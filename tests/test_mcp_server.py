"""Drives the MCP server through a real MCP client, in-process."""

import anyio
from mcp import Client
from sqlalchemy import select

from app.mcp_server import build_server
from app.models import Appointment
from tests.conftest import ANA, BRUNO


def run(coro):
    return anyio.run(coro)


def test_lists_all_agent_tools(db):
    async def go():
        async with Client(build_server(ANA)) as client:
            return {t.name for t in (await client.list_tools()).tools}

    assert run(go) == {
        "search_knowledge_base", "list_available_slots", "book_appointment", "get_my_appointments",
        "reschedule_appointment", "cancel_appointment", "create_payment_link", "get_exam_results",
        "escalate_to_human",
    }  # fmt: skip


def test_booking_through_mcp(db):
    async def go():
        async with Client(build_server(ANA)) as client:
            slots = await client.call_tool("list_available_slots", {"specialty": "Dermatology"})
            slot_id = slots.structured_content["slots"][0]["slot_id"]
            booked = await client.call_tool("book_appointment", {"slot_id": slot_id})
            return booked.structured_content

    booked = run(go)
    assert booked["specialty"] == "Dermatology" and booked["status"] == "scheduled"
    db.expire_all()
    assert db.get(Appointment, booked["appointment_id"]) is not None


def test_mcp_server_is_bound_to_one_patient(db):
    bruno_appt = db.scalar(select(Appointment).join(Appointment.patient).where(Appointment.status == "scheduled"))
    assert bruno_appt.patient.phone == BRUNO

    async def go():
        async with Client(build_server(ANA)) as client:
            return await client.call_tool("cancel_appointment", {"appointment_id": bruno_appt.id})

    result = run(go)
    assert result.is_error and "not found" in result.content[0].text
    db.expire_all()
    assert db.get(Appointment, bruno_appt.id).status == "scheduled"
