"""Data360-Memory. Run with:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Data360-Memory", page_icon="🧠", layout="wide")
nav = st.navigation([
    st.Page("pages/0_Overview.py", title="Overview", icon="🧠", default=True),
    st.Page("pages/1_Data_Explorer.py", title="Data Explorer", icon="🔎"),
    st.Page("pages/2_Chat_and_Memory.py", title="Chat and Memory", icon="💬"),
    st.Page("pages/3_Memory_Timeline.py", title="Memory Timeline", icon="🕒"),
    st.Page("pages/4_Evaluation.py", title="Evaluation", icon="📊"),
    st.Page("pages/5_Lab.py", title="Lab", icon="🧪"),
])
nav.run()
