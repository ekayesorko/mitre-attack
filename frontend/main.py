"""
NiceGUI frontend for MITRE: mitre, chat, and graph pages.
Chat page uses the backend /api/chat endpoint with local conversation history.
"""
import os
import httpx
from nicegui import ui

# Backend API base URL (e.g. http://localhost:8000 when running backend locally)
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
CHAT_API = f"{API_BASE.rstrip('/')}/api/chat/"


def add_nav():
    """Add navigation bar to current page."""
    with ui.header().classes("items-center gap-4 shadow"):
        ui.link("MITRE", "/mitre").classes("text-lg font-medium")
        ui.link("Chat", "/chat").classes("text-lg font-medium")
        ui.link("Graph", "/graph").classes("text-lg font-medium")


@ui.page("/")
def index():
    add_nav()
    ui.navigate.to("/chat")


@ui.page("/mitre")
def mitre_page():
    add_nav()
    with ui.column().classes("w-full max-w-2xl mx-auto mt-8 gap-4"):
        ui.label("MITRE").classes("text-2xl font-bold")
        ui.label("Coming soon.").classes("text-gray-500")


@ui.page("/chat")
def chat_page():
    add_nav()

    # Conversation history (local variable, no thread persistence)
    messages: list[dict[str, str]] = []

    async def send_message():
        text = (message_input.value or "").strip()
        if not text:
            return
        message_input.value = ""
        message_input.set_enabled(False)

        # Append user message and show in UI
        messages.append({"role": "user", "content": text})
        with chat_container:
            with ui.row().classes("w-full justify-end"):
                with ui.card().classes("max-w-[85%] sm:max-w-[80%] bg-primary text-primary-content"):
                    ui.label(text).classes("whitespace-pre-wrap break-words")
            assistant_row = ui.row().classes("w-full justify-start")
            spinner = ui.spinner("dots", size="sm")
            with assistant_row:
                with ui.card().classes("max-w-[85%] sm:max-w-[80%] bg-base-200"):
                    reply_md = ui.markdown("...").classes("break-words")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    CHAT_API,
                    json={"messages": messages, "system": None},
                )
            r.raise_for_status()
            data = r.json()
            reply = data.get("reply", "")
            model = data.get("model", "")
            messages.append({"role": "assistant", "content": reply})
            spinner.set_visibility(False)
            reply_md.content = reply or "(No response)"
            if model:
                with assistant_row:
                    ui.label(f"({model})").classes("text-xs text-gray-500")
        except httpx.HTTPStatusError as e:
            spinner.set_visibility(False)
            reply_md.content = f"**Error:** `{e.response.status_code}` — {e.response.text[:200]}"
        except Exception as e:
            spinner.set_visibility(False)
            reply_md.content = f"**Error:** {e!s}"
        finally:
            message_input.set_enabled(True)

    # Wrapper: fill viewport below header; column layout so only history scrolls
    page_height = "calc(100vh - 4rem)"
    with ui.column().classes("w-full").style(
        f"height: {page_height}; min-height: 0; display: flex; flex-direction: column;"
    ):
        # Scrollable history only
        with ui.element("div").classes("w-full min-h-0").style(
            "flex: 1 1 0; overflow-y: auto; overflow-x: hidden; -webkit-overflow-scrolling: touch;"
        ):
            chat_container = ui.column().classes("w-full gap-3 pt-4 px-3 sm:px-4 pb-0 min-h-full")
        # Input row: fixed at bottom, no gap above
        with ui.row().classes("w-full items-center gap-2 px-3 sm:px-4 pb-4 pt-0 bg-gray-100").style(
            "flex-shrink: 0;"
        ):
            message_input = (
                ui.input(placeholder="Type a message...")
                .classes("flex-1 min-w-0")
                .props("outlined rounded dense")
                .on("keydown.enter", send_message)
            )
            ui.button("Send", on_click=send_message).props("rounded flat")


@ui.page("/graph")
def graph_page():
    add_nav()
    with ui.column().classes("w-full max-w-2xl mx-auto mt-8 gap-4"):
        ui.label("Graph").classes("text-2xl font-bold")
        ui.label("Coming soon.").classes("text-gray-500")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="MITRE Frontend",
        port=8080,
        reload=False,
    )
