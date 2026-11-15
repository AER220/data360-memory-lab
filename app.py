"""Data360-Memory. Run with:  streamlit run app.py"""
# Entry point of the Streamlit app. Streamlit Community Cloud is set to run this file.
import streamlit as st

# Page settings are set once here, in the entry point, before any page runs.
st.set_page_config(page_title="Data360-Memory", page_icon="🧠", layout="wide")
# I list the pages explicitly with st.navigation so their order, titles and icons are fixed, instead
# of depending on file names.
nav = st.navigation([
    st.Page("pages/0_Overview.py", title="Overview", icon="🧠", default=True),
    st.Page("pages/1_Data_Explorer.py", title="Data Explorer", icon="🔎"),
    st.Page("pages/2_Chat_and_Memory.py", title="Chat and Memory", icon="💬"),
    st.Page("pages/3_Memory_Timeline.py", title="Memory Timeline", icon="🕒"),
    st.Page("pages/4_Evaluation.py", title="Evaluation", icon="📊"),
    st.Page("pages/5_Lab.py", title="Lab 9: Memory Lab", icon="🧪"),
])
# Run whichever page the user selected. Every page draws the shared sidebar, including the model
# switch.
nav.run()
