"""
NiceGUI frontend for MITRE: mitre, chat, and graph pages.
Chat page uses the backend /api/chat endpoint with local conversation history.
"""
import os
import httpx
from nicegui import ui

# Backend API base URL (e.g. http://localhost:8000 when running backend locally)
API_BASE = os.environ.get("API_BASE", "http://localhost:8000").rstrip("/")
CHAT_API = f"{API_BASE}/api/chat/"
SEARCH_API = f"{API_BASE}/api/search/"
GRAPH_SVG_URL = f"{API_BASE}/api/graph/svg"


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

    # Two-column layout: left = search + results, right = SVG slot
    page_height = "calc(100vh - 4rem)"
    with ui.row().classes("w-full gap-0").style(
        f"height: {page_height}; min-height: 0; align-items: stretch;"
    ):
        # Left panel: search bar + results
        with ui.column().classes("w-80 shrink-0 border-r border-gray-200 bg-base-200/30").style(
            "min-height: 0; overflow: hidden; display: flex; flex-direction: column;"
        ):
            ui.label("Search entities").classes("text-lg font-semibold pt-4 px-4")
            with ui.row().classes("w-full mx-4 mt-2 items-center gap-2"):
                search_input = (
                    ui.input(placeholder="Search by name or description...")
                    .classes("flex-1 min-w-0")
                    .props("outlined rounded dense clearable")
                )
                search_btn = ui.button("Search").props("rounded flat")

            results_container = ui.column().classes("w-full gap-2 mt-4 px-4 pb-4").style(
                "flex: 1 1 0; min-height: 0; overflow-y: auto;"
            )

        # Right panel: SVG slot
        with ui.column().classes("flex-1 min-w-0 bg-base-100").style(
            "min-height: 0; overflow: auto; display: flex; flex-direction: column;"
        ):
            svg_slot = ui.column().classes("w-full h-full min-h-[400px] p-4 items-center justify-center")
            with svg_slot:
                ui.label("Search and click a result to view its graph.").classes("text-gray-500")

    search_results: list[dict] = []

    async def do_search():
        q = (search_input.value or "").strip()
        if not q:
            return
        search_btn.set_enabled(False)
        results_container.clear()
        with results_container:
            ui.spinner("dots", size="sm")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(SEARCH_API, params={"q": q, "top_k": 10})
            r.raise_for_status()
            data = r.json()
            search_results.clear()
            search_results.extend(data.get("results", []))
        except httpx.HTTPStatusError as e:
            search_results.clear()
            search_results.append(
                {"error": f"{e.response.status_code} — {(e.response.text or '')[:200]}"}
            )
        except Exception as e:
            search_results.clear()
            search_results.append({"error": str(e)})
        finally:
            _render_results()
            search_btn.set_enabled(True)

    def _render_results():
        results_container.clear()
        with results_container:
            if not search_results:
                ui.label("No results.").classes("text-gray-500")
                return
            if len(search_results) == 1 and search_results[0].get("error"):
                ui.label(f"Error: {search_results[0]['error']}").classes("text-error")
                return
            for entry in search_results:
                name = entry.get("name") or entry.get("id") or "Unnamed"
                etype = entry.get("type") or ""
                score = entry.get("score")
                score_txt = f" {score:.2f}" if score is not None else ""
                def make_click_handler(ent):
                    async def handler():
                        await on_result_click(ent)
                    return handler

                with ui.card().classes("w-full cursor-pointer hover:bg-primary/10").on(
                    "click", make_click_handler(entry)
                ):
                    ui.label(name).classes("font-medium truncate")
                    if etype or score_txt:
                        ui.label(f"{etype}{score_txt}").classes("text-sm text-gray-500")

    async def on_result_click(entry: dict):
        stix_id = entry.get("id")
        if not stix_id:
            return
        svg_slot.clear()
        with svg_slot:
            ui.spinner("dots", size="lg")
        await _fetch_and_show_svg(stix_id)

    async def _fetch_and_show_svg(stix_id: str):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(GRAPH_SVG_URL, params={"stix_id": stix_id})
            r.raise_for_status()
            svg_text = r.text
        except httpx.HTTPStatusError as e:
            svg_text = None
            error_msg = f"{e.response.status_code} — {(e.response.text or '')[:300]}"
        except Exception as e:
            svg_text = None
            error_msg = str(e)
        else:
            error_msg = None

        svg_slot.clear()
        with svg_slot:
            if error_msg:
                ui.label(f"Failed to load graph: {error_msg}").classes("text-error max-w-xl")
            elif svg_text:
                ui.html(svg_text, sanitize=False).classes("w-full")
            else:
                ui.label("No graph data for this entity.").classes("text-gray-500")

    # Attach handlers after they are defined
    search_btn.on_click(do_search)
    search_input.on("keydown.enter", do_search)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="MITRE Frontend",
        port=8080,
        reload=False,
    )
