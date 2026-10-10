"""Page 6: Research Report. Cited report, exports, citation checks, follow-up Q&A and refinement."""
import re

import pandas as pd
import streamlit as st

from src.agents.qa import answer_question
from src.reporting.render import to_html, to_markdown, to_pdf
from src.services.llm import LLMClient
from src.ui.components import demo_banner, page_header
from src.ui.state import current_user, effective_settings, get_repo, preference, require_run

bundle = require_run()
repo, settings, user = get_repo(), effective_settings(), current_user()
report = bundle.report
page_header("Report", "Research Report", bundle.summary.question)
demo_banner(bundle.summary.mode)
if report is None:
    st.error("This run has no report (it may have failed). Its evidence can still be inspected on the other pages.")
    for error in bundle.errors:
        st.error(error)
    st.stop()

demo = bundle.summary.mode == "demo"
slug = re.sub(r"[^a-z0-9]+", "-", report.question.lower())[:50].strip("-") or "report"
e1, e2, e3, e4 = st.columns(4)
banner = demo and preference("include_demo_banner")
e1.download_button("Markdown", on_click=repo.log_activity, args=(user.id, "export", bundle.summary.id, {"format": "markdown"}), data=to_markdown(report, banner), file_name=f"{slug}.md", mime="text/markdown", icon=":material/download:",
                   width="stretch")
e2.download_button("HTML", on_click=repo.log_activity, args=(user.id, "export", bundle.summary.id, {"format": "html"}), data=to_html(report, banner), file_name=f"{slug}.html", mime="text/html", icon=":material/download:",
                   width="stretch")
if e3.button("Prepare PDF", width="stretch"):
    st.session_state[f"pdf_{bundle.summary.id}"] = to_pdf(report, banner)
pdf = st.session_state.get(f"pdf_{bundle.summary.id}")
if pdf:
    e3.download_button("PDF", on_click=repo.log_activity, args=(user.id, "export", bundle.summary.id, {"format": "pdf"}), data=pdf, file_name=f"{slug}.pdf", mime="application/pdf", icon=":material/download:", width="stretch")
elif f"pdf_{bundle.summary.id}" in st.session_state:
    e3.caption("PDF rendering failed. Use HTML and print to PDF.")
if e4.button("Refine investigation", icon=":material/replay:", width="stretch"):
    findings = (report.section("key_findings").content if report.section("key_findings") else "")[:1500]
    st.session_state["refine_draft"] = {
        "question": bundle.summary.question, "parent_run_id": bundle.summary.id,
        "context": f"Refining a previous investigation. Earlier findings (verify, don't assume):\n{findings}"}
    st.switch_page("pages/1_Research_Workspace.py")

st.header(report.title)
st.caption(f"Generated {report.created_at:%d %b %Y %H:%M} · {report.generated_by} · {len(report.references)} references")
toc = [s for s in report.sections]
with st.expander("Contents"):
    st.markdown("\n".join(f"{i}. {s.title}" for i, s in enumerate(toc, start=1)))
refs = {r["n"]: r for r in report.references}
for section in report.sections:
    st.subheader(section.title)
    if section.key == "references":
        for r in report.references:
            line = f"**[{r['n']}]** {r['label']}"
            if r.get("url"):
                line += f" · [{'link (synthetic)' if r['synthetic'] else 'link'}]({r['url']})"
            tags = [r["origin_label"]] + ([] if r["full_text_reviewed"] else ["abstract/snippet only"])
            st.markdown(line + f"  \n<span class='dr-muted'>{' · '.join(tags)}</span>", unsafe_allow_html=True)
    else:
        st.markdown(section.content)

checks = report.citation_checks
with st.expander(f"Citation traceability: {sum(c.valid for c in checks)}/{len(checks)} citations passed"):
    st.caption("Checks that each cited source exists in the corpus, that the reference entry matches the source record, "
               "that the cited passage is relevant to the sentence, and that the citation renders. Traceability does "
               "**not** establish that a claim is true.")
    if checks:
        st.dataframe(pd.DataFrame([{"Marker": c.marker, "Source exists": c.exists, "Reference matches": c.reference_matches,
                                    "Passage relevant": c.passage_relevant, "Renders": c.renderable, "Note": c.note}
                                   for c in checks]), hide_index=True, width="stretch")

st.divider()
st.subheader("Ask about this investigation")
st.caption("Answers come from this run's evidence (claims, evidence matrix and source passages), not just the report.")
history = repo.list_qa(bundle.summary.id, user.id)
for item in history:
    with st.chat_message("user"):
        st.markdown(item["question"])
    with st.chat_message("assistant", avatar=":material/science:"):
        answer = item["answer"]
        st.markdown(answer["answer"])
        st.caption(f"Basis: {answer['basis']} · {answer['method']}")
llm = LLMClient(settings) if settings.llm_configured else None
use_llm = st.toggle("Use LLM for answers", value=bool(llm) and bundle.summary.mode == "live", disabled=llm is None,
                    help="Answers are always grounded in this run's evidence; citations are validated.")
question = st.chat_input("e.g. Which sources disagree about adoption rates, and why?")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar=":material/science:"):
        with st.spinner("Retrieving evidence…"):
            answer = answer_question(bundle, question, llm=llm, use_llm=use_llm)
        st.markdown(answer.answer)
        if answer.conflicts:
            st.markdown("**Conflicting evidence:**\n" + "\n".join(f"- {c}" for c in answer.conflicts))
        if answer.gaps:
            st.markdown("**Missing evidence:**\n" + "\n".join(f"- {g}" for g in answer.gaps))
        if answer.general_knowledge_note:
            st.info(f"General knowledge (not from the research corpus): {answer.general_knowledge_note}")
        with st.expander(f"Sources ({len(answer.citations)}) and how this answer was reached"):
            st.caption(answer.how_reached)
            for c in answer.citations:
                st.markdown(f"**[{c['n']}]** {c['label']} · {c['origin']}" + (f" · {c['location']}" if c["location"] else "")
                            + (f"\n\n> {c['passage']}" if c["passage"] else ""))
        st.caption(f"Basis: {answer.basis} · {answer.method}")
    repo.save_qa(bundle.summary.id, question, answer.model_dump(), user.id)
    repo.log_activity(user.id, "qa", bundle.summary.id, {"question": question[:200]})
