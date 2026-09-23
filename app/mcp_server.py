"""MCP server: exposes ClinicFlow's tools to any Model Context Protocol client
(Claude Desktop, Claude Code, IDE agents, other LLM apps).

The same authorization rule as the WhatsApp agent applies: the server is bound
to ONE patient, chosen by whoever launches it (CLINICFLOW_MCP_PHONE), never by
the model. Every call runs the exact tool implementation the agent uses.

Run over stdio:
    CLINICFLOW_MCP_PHONE=+5562991110001 python -m app.mcp_server
"""

import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app import crm
from app.agent.tools import ToolContext, run_tool
from app.db import SessionLocal, init_db


def build_server(phone: str) -> MCPServer:
    server = MCPServer(
        name="clinicflow",
        instructions=(
            "Tools for one clinic patient: answer clinic questions from the knowledge base, "
            "manage appointments, create Stripe payment links and read released lab results. "
            "Never give medical advice."
        ),
    )

    def call(name: str, **args: Any) -> dict[str, Any]:
        with SessionLocal() as db:
            patient = crm.find_patient_by_phone(db, phone)
            if patient is None:
                raise ToolError(f"No patient registered for {phone}")
            result, is_error = run_tool(ToolContext(db, patient), name, args)
            if is_error:
                db.rollback()
                raise ToolError(result["error"])
            db.commit()
            return result

    @server.tool()
    def search_knowledge_base(query: str) -> dict[str, Any]:
        """Search the clinic knowledge base (hours, location, insurance, prices, exam preparation, policies)."""
        return call("search_knowledge_base", query=query)

    @server.tool()
    def list_available_slots(specialty: str, day: str | None = None) -> dict[str, Any]:
        """List open appointment slots for a specialty, optionally on a day (YYYY-MM-DD)."""
        return call("list_available_slots", specialty=specialty, **({"day": day} if day else {}))

    @server.tool()
    def book_appointment(slot_id: int) -> dict[str, Any]:
        """Book an open slot for the patient."""
        return call("book_appointment", slot_id=slot_id)

    @server.tool()
    def get_my_appointments() -> dict[str, Any]:
        """List the patient's upcoming appointments with payment status."""
        return call("get_my_appointments")

    @server.tool()
    def reschedule_appointment(appointment_id: int, new_slot_id: int) -> dict[str, Any]:
        """Move one of the patient's appointments to another open slot."""
        return call("reschedule_appointment", appointment_id=appointment_id, new_slot_id=new_slot_id)

    @server.tool()
    def cancel_appointment(appointment_id: int) -> dict[str, Any]:
        """Cancel one of the patient's appointments."""
        return call("cancel_appointment", appointment_id=appointment_id)

    @server.tool()
    def create_payment_link(appointment_id: int) -> dict[str, Any]:
        """Create (or reuse) a Stripe payment link for an appointment."""
        return call("create_payment_link", appointment_id=appointment_id)

    @server.tool()
    def get_exam_results() -> dict[str, Any]:
        """Get the patient's lab results; unreleased results are reported as processing."""
        return call("get_exam_results")

    @server.tool()
    def escalate_to_human(reason: str) -> dict[str, Any]:
        """Hand the conversation to clinic staff."""
        return call("escalate_to_human", reason=reason)

    return server


def main() -> None:
    phone = os.environ.get("CLINICFLOW_MCP_PHONE")
    if not phone:
        raise SystemExit("Set CLINICFLOW_MCP_PHONE to the patient's phone number, e.g. +5562991110001")
    init_db()
    build_server(phone).run("stdio")


if __name__ == "__main__":
    main()
