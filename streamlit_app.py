import re
from typing import Dict, List, Optional

import requests
import streamlit as st


# --- App constants
BACKEND_BASE_URL = "https://dominant-usually-oyster.ngrok-free.app"


st.set_page_config(
    page_title="VishNet – AI Powered Vishing Simulation & Defense",
    page_icon="📞",
    layout="centered",
)


# --- Data fetching helpers
@st.cache_data(ttl=30, show_spinner=False)
def fetch_personas() -> Dict[str, List[str]]:
    """Fetch personas from backend.

    Returns a dict: {"normal": [...], "impersonation": [...]}.
    Raises RuntimeError on any failure.
    """
    try:
        resp = requests.get(f"{BACKEND_BASE_URL}/personas", timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        personas = data.get("personas") or {}
        return {
            "normal": list(personas.get("normal") or []),
            "impersonation": list(personas.get("impersonation") or []),
        }
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch personas: {e}") from e
    except ValueError as e:
        raise RuntimeError("Invalid response while fetching personas") from e


def refresh_personas() -> Dict[str, List[str]]:
    """Clear the cache and refetch personas."""
    fetch_personas.clear()
    return fetch_personas()


def validate_phone(ph: str) -> tuple[bool, str]:
    """Basic E.164 phone validation.

    Accepts forms like +15551234567 (8–15 digits total, leading + optional).
    """
    if not ph:
        return False, "Phone number is required."
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", ph):
        return False, "Enter a valid E.164 phone (e.g., +15551234567)."
    return True, ""


def place_call(
    ph: str,
    name: str,
    persona: str,
    mode: str,
    voice_id: Optional[str] = None,
) -> dict:
    """POST /call to initiate a vishing simulation call."""
    payload = {"ph": ph, "name": name, "persona": persona, "mode": mode}
    if voice_id:
        payload["voice_id"] = voice_id
    try:
        resp = requests.post(f"{BACKEND_BASE_URL}/call", json=payload, timeout=30)
        # Try reading JSON either way for helpful messages
        content = None
        try:
            content = resp.json()
        except Exception:
            content = None

        if resp.status_code >= 400:
            message = None
            if isinstance(content, dict):
                message = (
                    content.get("message")
                    or content.get("error")
                    or content.get("detail")
                )
            raise RuntimeError(message or f"Server error: HTTP {resp.status_code}")

        return content or {"success": True}
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to place call: {e}") from e


# --- UI
st.title("VishNet – AI Powered Vishing Simulation & Defence")
st.caption(f"Backend: {BACKEND_BASE_URL}")


# Prefetch personas on first load
if "personas" not in st.session_state:
    try:
        with st.spinner("Loading personas…"):
            st.session_state["personas"] = fetch_personas()
    except Exception as e:
        st.session_state["personas"] = {"normal": [], "impersonation": []}
        st.error(str(e))


st.subheader("Place a call")
st.write(
    "Fill in the target details, choose a mode and persona, then press Place call."
)

# Lightweight refresh button to re-fetch personas (for new impersonation voices)
refresh = st.button("Refresh personas", help="Refetch personas (normal & impersonation) from the server")
if refresh:
    try:
        with st.spinner("Refreshing personas…"):
            st.session_state["personas"] = refresh_personas()
        st.toast("Personas refreshed", icon="🔄")
    except Exception as e:
        st.error(str(e))

# Move mode selector OUTSIDE the form so changing it updates the persona list immediately
mode = st.radio(
    "Mode",
    options=["normal", "impersonation"],
    index=0 if st.session_state.get("mode", "normal") == "normal" else 1,
    horizontal=True,
    key="mode",
    help="Normal: preset personas. Impersonation: dynamically cloned voices (refresh after a call).",
)

with st.form("place_call_form", clear_on_submit=False, border=True):
    ph = st.text_input("Target phone (E.164)", placeholder="+15551234567")
    name = st.text_input("Target name", placeholder="Jane Doe")
    # Use the selected mode from session state so the selectbox updates on toggle
    personas = st.session_state.get("personas", {"normal": [], "impersonation": []})
    current_mode = st.session_state.get("mode", "normal")
    persona_choices = personas.get(current_mode) or []
    disabled = len(persona_choices) == 0
    persona = st.selectbox(
        "Persona",
        persona_choices if not disabled else ["(No personas available)"],
        index=0,
        disabled=disabled,
        help="Select a persona. Use the Refresh button after a successful call to load new impersonation voices.",
    )

    # Optional ElevenLabs voice ID for normal mode only
    is_normal_mode = current_mode == "normal"
    voice_id = st.text_input(
        "ElevenLabs voice ID (optional)",
        value=("UgBBYS2sOqTuMpoF3BR0" if is_normal_mode else ""),
        placeholder="UgBBYS2sOqTuMpoF3BR0",
        disabled=not is_normal_mode,
        help=(
            "Provide a specific voice for normal mode."
        ),
    )
    if is_normal_mode:
        st.caption(
            "Reference: Twilio TTS voices and languages – https://www.twilio.com/docs/voice/twiml/say/text-speech#available-voices-and-languages"
        )

    submitted = st.form_submit_button("Place call", type="primary")

    if submitted:
        ok, msg = validate_phone(ph)
        if not ok:
            st.error(msg)
        elif not name.strip():
            st.error("Name is required.")
        elif disabled:
            st.error("No personas available for the selected mode. Try Refresh personas.")
        else:
            with st.spinner("Placing call…"):
                try:
                    to_send_voice = voice_id.strip() if (is_normal_mode and voice_id and voice_id.strip()) else None
                    result = place_call(
                        ph=ph.strip(),
                        name=name.strip(),
                        persona=persona,
                        mode=current_mode,
                        voice_id=to_send_voice,
                    )
                except Exception as e:
                    st.error(str(e))
                else:
                    st.success("Call requested. You should receive the call shortly.")
                    st.toast("Call created on server", icon="✅")
                    with st.expander("Request details"):
                        details = {
                            "ph": ph.strip(),
                            "name": name.strip(),
                            "persona": persona,
                            "mode": current_mode,
                        }
                        if to_send_voice:
                            details["voice_id"] = to_send_voice
                        st.json(details)

