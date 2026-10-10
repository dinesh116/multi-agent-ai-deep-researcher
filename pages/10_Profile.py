"""Update profile: name, age, sex, education, occupation and research interests."""
import streamlit as st
from pydantic import ValidationError

from src.models.user import EDUCATION_OPTIONS, INTEREST_OPTIONS, SEX_OPTIONS, UserProfile
from src.ui.components import page_header
from src.ui.state import get_repo, require_user

user = require_user()
repo = get_repo()
profile = user.profile
page_header("Account", "Update profile", "Tell us a little about yourself. Your profile is stored with your account and "
                                         "is never sent to search providers or the LLM.")

with st.form("profile"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Display name", value=user.name, max_chars=80)
    c2.text_input("Email", value=user.email, disabled=True, help=f"Signed in with {user.provider_label}.")
    age = c1.number_input("Age", min_value=13, max_value=120, value=profile.age, step=1, placeholder="Prefer not to say")
    sex = c2.selectbox("Sex", SEX_OPTIONS, index=SEX_OPTIONS.index(profile.sex) if profile.sex else None,
                       placeholder="Choose an option")
    education = c1.selectbox("Highest education", EDUCATION_OPTIONS,
                             index=EDUCATION_OPTIONS.index(profile.education) if profile.education else None,
                             placeholder="Choose an option")
    occupation = c2.text_input("Occupation or role", value=profile.occupation, max_chars=120,
                               placeholder="e.g. Product manager, PhD student")
    known = list(dict.fromkeys(INTEREST_OPTIONS + profile.interests))
    interests = st.multiselect("Research interests", known, default=[i for i in profile.interests if i in known])
    extra = st.text_input("Other interests", placeholder="Comma-separated, e.g. robotics, public health")
    saved = st.form_submit_button("Save profile", type="primary", icon=":material/save:")

if saved:
    try:
        updated = UserProfile(age=int(age) if age is not None else None, sex=sex, education=education,
                              occupation=occupation, interests=interests + [i for i in extra.split(",") if i.strip()])
    except ValidationError as exc:
        for error in exc.errors():
            st.error(f"{error['loc'][0]}: {error['msg']}")
    else:
        if not name.strip():
            st.error("Please enter a display name.")
        else:
            repo.update_user(user.id, name, updated)
            st.toast("Profile saved.", icon=":material/check_circle:")
            st.rerun()

st.caption(f"Member since {user.created_at:%d %b %Y} · signed in with {user.provider_label}.")
