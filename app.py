from dotenv import load_dotenv
import os

load_dotenv()
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import plotly.express as px
from openai import OpenAI
import os

# ======================
# CONFIG
# ======================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ======================
# DATABASE
# ======================
DB_PATH = os.path.join(os.getcwd(), "barbershop.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# ======================
# TABLES
# ======================
c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS records (date TEXT, barber TEXT, service TEXT, amount INTEGER, payment_method TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS services (name TEXT PRIMARY KEY)")
conn.commit()

# ======================
# DEFAULT DATA
# ======================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

if not c.execute("SELECT * FROM users").fetchall():
    c.execute("INSERT INTO users VALUES (?,?,?)", ("admin", hash_password("admin"), "admin"))

if not c.execute("SELECT * FROM services").fetchall():
    for s in ["Haircut","Shave","Dreadlocks"]:
        c.execute("INSERT INTO services VALUES (?)", (s,))
conn.commit()

# ======================
# LOGIN
# ======================
if "logged" not in st.session_state:
    st.session_state.logged = False

if not st.session_state.logged:
    st.title("🔐 Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = c.execute("SELECT * FROM users WHERE username=? AND password=?",
                         (u, hash_password(p))).fetchone()
        if user:
            st.session_state.logged = True
            st.session_state.user = user[0]
            st.session_state.role = user[2]
            st.rerun()
        else:
            st.error("Invalid login")
    st.stop()

# ======================
# LOAD DATA
# ======================
df_all = pd.read_sql_query("SELECT rowid,* FROM records", conn)

if not df_all.empty:
    df_all["date"] = pd.to_datetime(df_all["date"], errors="coerce")

# ======================
# FILTER (SAFE)
# ======================
st.sidebar.subheader("📅 Date Filter")

today = datetime.today().date()
start = st.sidebar.date_input("Start", today - timedelta(days=30))
end = st.sidebar.date_input("End", today)

df = df_all.copy()

if not df.empty:
    df = df[(df["date"]>=pd.to_datetime(start)) & (df["date"]<=pd.to_datetime(end))]

# ROLE
is_admin = st.session_state.role == "admin"
fdf = df if is_admin else df[df["barber"] == st.session_state.user]

# ======================
# NAVIGATION
# ======================
if is_admin:
    pages = ["Dashboard","Add Record","Analytics","Leaderboard","Performance","Edit Records","Services","Admin","AI"]
else:
    pages = ["Dashboard","Add Record","Analytics","Edit Records","AI"]

page = st.sidebar.radio("Menu", pages)

# ======================
# DASHBOARD
# ======================
if page == "Dashboard":
    st.title("📊 Dashboard")

    if fdf.empty:
        st.warning("No data")
    else:
        if is_admin:
            st.metric("Total Revenue", f"KES {df['amount'].sum():,}")

            perf = df_all.groupby("barber")["amount"].sum().reset_index()
            perf["earnings"] = perf["amount"] * 0.4
            st.dataframe(perf)
        else:
            fdf["date"] = fdf["date"].dt.date

            daily = fdf[fdf["date"]==today]["amount"].sum()
            weekly = fdf[fdf["date"]>=today-timedelta(days=7)]["amount"].sum()
            monthly = fdf[fdf["date"]>=today.replace(day=1)]["amount"].sum()

            col1,col2,col3 = st.columns(3)
            col1.metric("Today", f"KES {daily*0.4:,.0f}")
            col2.metric("Week", f"KES {weekly*0.4:,.0f}")
            col3.metric("Month", f"KES {monthly*0.4:,.0f}")

# ======================
# ADD RECORD
# ======================
elif page == "Add Record":
    st.title("➕ Add Record")

    services = pd.read_sql_query("SELECT name FROM services", conn)["name"].tolist()

    date = st.date_input("Date", today)
    service = st.selectbox("Service", services)
    amount = st.number_input("Amount", min_value=1)

    if st.button("Save"):
        c.execute("INSERT INTO records VALUES (?,?,?,?,?)",
                  (date.strftime("%Y-%m-%d"), st.session_state.user, service, amount, "Cash"))
        conn.commit()
        st.success("Saved")
        st.rerun()

# ======================
# ANALYTICS
# ======================
elif page == "Analytics":
    st.title("📊 Analytics")

    if fdf.empty:
        st.warning("No data")
    else:
        st.plotly_chart(px.bar(fdf["service"].value_counts()))

# ======================
# LEADERBOARD
# ======================
elif page == "Leaderboard":
    if is_admin:
        st.title("🏆 Leaderboard")

        if df_all.empty:
            st.warning("No data")
        else:
            st.dataframe(df_all.groupby("barber")["amount"].sum())

# ======================
# PERFORMANCE
# ======================
elif page == "Performance":
    if is_admin:
        st.title("💈 Performance")

        if df_all.empty:
            st.warning("No data")
        else:
            st.dataframe(df_all.groupby("barber")["amount"].agg(["sum","count"]))

# ======================
# EDIT RECORDS
# ======================
elif page == "Edit Records":
    st.title("✏️ Edit Records")

    if fdf.empty:
        st.warning("No records")
    else:
        st.dataframe(fdf)

        rid = st.selectbox("Select Record", fdf["rowid"])
        rec = c.execute("SELECT rowid,* FROM records WHERE rowid=?", (rid,)).fetchone()

        new_service = st.text_input("Service", rec[3])
        new_amount = st.number_input("Amount", value=int(rec[4]))

        rec_date = pd.to_datetime(rec[1]).date()
        can_edit = is_admin or rec_date == today

        if can_edit:
            if st.button("Update"):
                c.execute("UPDATE records SET service=?, amount=? WHERE rowid=?",
                          (new_service, new_amount, rid))
                conn.commit()
                st.success("Updated")
                st.rerun()

            if st.button("Delete"):
                c.execute("DELETE FROM records WHERE rowid=?", (rid,))
                conn.commit()
                st.success("Deleted")
                st.rerun()

# ======================
# ADMIN
# ======================
elif page == "Admin":
    if is_admin:
        st.title("👨‍💼 Admin Panel")

        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["barber","admin"])

        if st.button("Create User"):
            try:
                c.execute("INSERT INTO users VALUES (?,?,?)",
                          (u, hash_password(p), role))
                conn.commit()
                st.success("Created")
                st.rerun()
            except:
                st.error("Exists")

        users = pd.read_sql_query("SELECT * FROM users", conn)
        st.dataframe(users)

        if not users.empty:
            udel = st.selectbox("Delete User", users["username"])

            if st.button("Delete User"):
                if udel == "admin" or udel == st.session_state.user:
                    st.error("Not allowed")
                else:
                    c.execute("DELETE FROM users WHERE username=?", (udel,))
                    conn.commit()
                    st.success("Deleted")
                    st.rerun()

# ======================
# AI (FULL CHAT)
# ======================
elif page == "AI":
    st.title("🤖 AI Assistant")

    if fdf.empty:
        st.warning("No data")
    else:
        context = f"Revenue: {fdf['amount'].sum()}"

        if st.button("Generate Insights"):
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":context}]
            )
            st.write(res.choices[0].message.content)

        if "chat" not in st.session_state:
            st.session_state.chat = []

        msg = st.text_input("Ask AI")

        if st.button("Send"):
            st.session_state.chat.append({"role":"user","content":msg})

            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=st.session_state.chat
            )

            reply = res.choices[0].message.content
            st.session_state.chat.append({"role":"assistant","content":reply})

        for m in st.session_state.chat:
            st.write(f"**{m['role']}**: {m['content']}")