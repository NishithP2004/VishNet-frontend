import re
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

import requests
import streamlit as st


# --- App constants
DEFAULT_BACKEND_URL = "https://dominant-usually-oyster.ngrok-free.app"


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
        backend_url = st.session_state.get("backend_url", DEFAULT_BACKEND_URL)
        resp = requests.get(f"{backend_url}/personas", timeout=15)
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


def format_timestamp(timestamp) -> str:
    """Convert timestamp (milliseconds) to readable date string in IST.
    
    Args:
        timestamp: Unix timestamp in milliseconds (can be int, float, or string)
    
    Returns:
        Formatted date string in IST (e.g., "Dec 31, 2025 at 3:45 PM IST")
    """
    if not timestamp:
        return "N/A"
    try:
        # Convert to float if it's a string
        ts = float(timestamp)
        if ts == 0:
            return "N/A"
        # Create IST timezone (UTC+5:30)
        ist = timezone(timedelta(hours=5, minutes=30))
        # Convert from milliseconds to seconds and create datetime in IST
        dt = datetime.fromtimestamp(ts / 1000, tz=ist)
        return dt.strftime("%b %d, %Y at %I:%M %p IST")
    except (ValueError, TypeError, OSError):
        return "N/A"


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
        backend_url = st.session_state.get("backend_url", DEFAULT_BACKEND_URL)
        resp = requests.post(f"{backend_url}/call", json=payload, timeout=30)
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


def fetch_calls() -> List[dict]:
    """Fetch list of all calls from backend, sorted by timestamp (newest first).
    
    Returns a list of dicts with: name, ph, callSid, timestamp (sorted descending).
    Raises RuntimeError on any failure.
    """
    try:
        backend_url = st.session_state.get("backend_url", DEFAULT_BACKEND_URL)
        resp = requests.get(f"{backend_url}/calls", timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        calls = data.get("calls") or []
        
        # Fetch timestamp for each call and sort by timestamp (newest first)
        calls_with_timestamps = []
        for call in calls:
            try:
                call_details = fetch_call_details(call["callSid"])
                timestamp = call_details.get("timestamp", 0)
                calls_with_timestamps.append({
                    **call,
                    "timestamp": timestamp
                })
            except Exception:
                # If timestamp fetch fails, use 0 as fallback
                calls_with_timestamps.append({
                    **call,
                    "timestamp": 0
                })
        
        # Sort by timestamp descending (newest first)
        sorted_calls = sorted(calls_with_timestamps, key=lambda x: x.get("timestamp", 0), reverse=True)
        return sorted_calls
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch calls: {e}") from e
    except ValueError as e:
        raise RuntimeError("Invalid response while fetching calls") from e


def fetch_call_details(call_sid: str) -> dict:
    """Fetch full details for a specific call.
    
    Returns the call data dict.
    Raises RuntimeError on any failure.
    """
    try:
        backend_url = st.session_state.get("backend_url", DEFAULT_BACKEND_URL)
        resp = requests.get(f"{backend_url}/calls/{call_sid}", timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        if not data.get("success"):
            raise RuntimeError(data.get("error", "Failed to fetch call details"))
        return data.get("data") or {}
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch call details: {e}") from e
    except ValueError as e:
        raise RuntimeError("Invalid response while fetching call details") from e


def fetch_report(call_sid: str) -> dict:
    """Fetch report data for a specific call.
    
    Returns a dict with: report (markdown), transcript, name, ph.
    Raises RuntimeError on any failure.
    """
    try:
        backend_url = st.session_state.get("backend_url", DEFAULT_BACKEND_URL)
        resp = requests.get(f"{backend_url}/reports/{call_sid}", timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        if not data.get("success"):
            raise RuntimeError(data.get("error", "Failed to fetch report"))
        return data.get("data") or {}
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch report: {e}") from e
    except ValueError as e:
        raise RuntimeError("Invalid response while fetching report") from e


# --- UI
st.title("VishNet – AI Powered Vishing Simulation & Defence")

# Initialize backend URL in session state
if "backend_url" not in st.session_state:
    st.session_state["backend_url"] = DEFAULT_BACKEND_URL

# Sidebar for backend URL configuration
with st.sidebar:
    st.subheader("⚙️ Settings")
    backend_url = st.text_input(
        "Backend URL",
        value=st.session_state.get("backend_url", DEFAULT_BACKEND_URL),
        help="Enter the backend server URL (e.g., https://api.example.com)",
    )
    if backend_url != st.session_state.get("backend_url", DEFAULT_BACKEND_URL):
        st.session_state["backend_url"] = backend_url
        # Clear personas cache when URL changes
        if "personas" in st.session_state:
            del st.session_state["personas"]
        st.rerun()
    
    if st.button("Reset to default", help="Reset backend URL to default"):
        st.session_state["backend_url"] = DEFAULT_BACKEND_URL
        if "personas" in st.session_state:
            del st.session_state["personas"]
        st.rerun()

st.caption(f"Backend: {st.session_state.get('backend_url', DEFAULT_BACKEND_URL)}")


# Prefetch personas on first load
if "personas" not in st.session_state:
    try:
        with st.spinner("Loading personas…"):
            st.session_state["personas"] = fetch_personas()
    except Exception as e:
        st.session_state["personas"] = {"normal": [], "impersonation": []}
        st.error(str(e))


# Create tabs for different sections
tab1, tab2 = st.tabs(["Place Call", "View Calls & Reports"])

with tab1:
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

        st.markdown(
            "**Consent notice**"
        )
        st.info(
            "By placing this vishing simulation call, you confirm you have permission to contact the target number and that all participants consent to training/assessment."
        )
        consent_ack = st.checkbox(
            "I understand and have obtained consent to run this simulation.",
            help="Required before submitting."
        )

        submitted = st.form_submit_button("Place call", type="primary")

        if submitted:
            ok, msg = validate_phone(ph)
            if not ok:
                st.error(msg)
            elif not name.strip():
                st.error("Name is required.")
            elif not consent_ack:
                st.error("Please acknowledge consent before placing the call.")
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

with tab2:
    st.subheader("View Calls & Reports")
    st.write("Search, filter, and view call details and reports.")
    
    # Refresh button for calls list
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh", help="Reload the list of calls from the server", use_container_width=True):
            st.rerun()
    
    try:
        with st.spinner("Loading calls…"):
            calls = fetch_calls()
        
        if not calls:
            st.info("No calls found. Place a call first using the 'Place Call' tab.")
        else:
            # Search and filter section
            search_col1, search_col2 = st.columns(2)
            with search_col1:
                search_query = st.text_input(
                    "🔍 Search by name or phone",
                    placeholder="Enter name or phone number...",
                    help="Filter calls by target name or phone number"
                )
            
            # Filter calls based on search query
            filtered_calls = calls
            if search_query.strip():
                search_lower = search_query.lower()
                filtered_calls = [
                    call for call in calls
                    if search_lower in call.get("name", "").lower() 
                    or search_lower in call.get("ph", "").lower()
                ]
            
            # Display call count
            st.caption(f"📊 Showing {len(filtered_calls)} of {len(calls)} calls")
            
            if not filtered_calls:
                st.warning("No calls match your search criteria.")
            else:
                # Create a display name for each call with timestamp
                call_options = [f"{call['name']} • {call['ph']} • {format_timestamp(call.get('timestamp', 0))}" for call in filtered_calls]
                selected_idx = st.selectbox(
                    "Select a call to view details",
                    range(len(filtered_calls)),
                    format_func=lambda i: call_options[i],
                    key="call_selector"
                )
                
                selected_call = filtered_calls[selected_idx]
                call_sid = selected_call["callSid"]
                
                st.divider()
                
                # Create sub-tabs for details and report
                details_tab, report_tab = st.tabs(["📋 Call Details", "📄 Report"])
                
                with details_tab:
                    try:
                        with st.spinner("Loading call details…"):
                            call_data = fetch_call_details(call_sid)
                        
                        # Display call details without truncation
                        st.markdown("#### Call Information")
                        st.write(f"**Name:** {call_data.get('name', 'N/A')}")
                        st.write(f"**Phone:** {call_data.get('ph', call_data.get('phone', 'N/A'))}")
                        st.write(f"**Mode:** {call_data.get('mode', 'N/A')}")
                        st.write(f"**Persona:** {call_data.get('persona', 'N/A')}")
                        st.write(f"**Call SID:** {call_sid}")
                        
                        # Display timestamp if available
                        timestamp = call_data.get("timestamp", 0)
                        if timestamp:
                            st.write(f"**Date & Time:** {format_timestamp(timestamp)}")
                        
                        # Display voice_id if available
                        voice_id = call_data.get("voice_id")
                        if voice_id:
                            st.write(f"**Voice ID:** {voice_id}")
                        
                        st.divider()
                        
                        # Display additional fields in an expander
                        with st.expander("📊 Full call data (JSON)"):
                            st.json(call_data)
                        
                    except Exception as e:
                        st.error(f"Failed to load call details: {e}")
                
                with report_tab:
                    try:
                        with st.spinner("Loading report…"):
                            report_data = fetch_report(call_sid)
                        
                        # Display report as markdown
                        report_content = report_data.get("report", "")
                        if report_content and report_content != "Report not found for the given CallSid":
                            st.markdown(report_content)
                        else:
                            st.warning("⏳ Report not available yet. The call may still be processing.")
                        
                        # Display transcript
                        transcript = report_data.get("transcript", "")
                        if transcript:
                            with st.expander("📝 View transcript"):
                                st.text_area(
                                    "Transcript",
                                    value=transcript,
                                    height=200,
                                    disabled=True,
                                    label_visibility="collapsed"
                                )
                        
                        # Display other report details
                        with st.expander("📋 Report metadata"):
                            metadata = {
                                "name": report_data.get("name"),
                                "phone": report_data.get("ph"),
                                "callSid": call_sid,
                            }
                            st.json(metadata)
                    
                    except Exception as e:
                        st.error(f"Failed to load report: {e}")
    
    except Exception as e:
        st.error(f"Failed to fetch calls list: {e}")

