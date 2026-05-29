# Each item: group, page_path, label, roles_allowed
NAV_REGISTRY = [
    # --- Meeting Intelligence ---
    ("🧠 Meeting Intelligence", "pages/1_NFR_Generator.py", "🧾 Daily NFR Generator", {"admin", "user", "viewer"}),
    ("🧠 Meeting Intelligence", "pages/2_Weekly_NFR.py", "📘 Weekly NFR Consolidator", {"admin", "user", "viewer"}),

    # --- RAID & Action ---
    ("⚠️ RAID & Action Management", "pages/3_RAID_Log_Assistant.py", "📌 RAID Log Assistant", {"admin", "user", "viewer"}),
    ("⚠️ RAID & Action Management", "pages/4_Action_Manager.py", "📝 Action Register Manager", {"admin", "user", "viewer"}),

    # --- Reporting & Governance ---
    ("📄 Reporting & Governance", "pages/5_Governance_Pack_Dashboard.py", "📊 Governance Pack Dashboard", {"admin", "user", "viewer"}),
    ("📄 Reporting & Governance", "pages/15_Template_Library.py", "📂 Template Library", {"admin", "user", "viewer"}),

    # --- Coming soon ---
    ("🚀 Coming Soon", "pages/7_Sharepoint_Connector.py", "🔧 SharePoint Connector", {"admin", "user"}),
    ("🚀 Coming Soon", "pages/8_Notifications_Manager.py", "📬 Email Generator", {"admin", "user"}),

    # --- User Tools ---
    ("👤 User Tools", "pages/6_Project_Configuration.py", "⚙️ Project Configuration Manager", {"admin", "user"}),
    ("👤 User Tools", "pages/10_My_Profile.py", "👤 My Profile", {"admin", "user", "ceo", "exec"}),
    ("👤 User Tools", "pages/13_Project_Submission_Tracker.py", "🧮 Project Submission Tracker", {"admin", "user"}),
    ("👤 User Tools", "pages/16_User_Help_Guide.py", "🗃️ User Help Guide", {"admin", "user", "viewer", "ceo", "exec"}),
    ("👤 User Tools", "pages/28_Resource_Allocation_Manager.py", "🧑‍🔧 Resource Allocation Manager", {"admin", "exec", "user"}),
    ("👤 User Tools", "pages/29_Project_Gannt.py", "📅 Gannt Chart Builder", {"admin", "exec", "user"}),

    # --- CEO ---
    ("CEO Tools", "pages/23_RAIDs_Log.py", "💡 Project Health", {"admin", "ceo"}),
    ("CEO Tools", "pages/24_CEO_Client_Performance.py", "🏢 Client Performance", {"admin", "ceo"}),

    # --- Exec ---
    ("Executive Tools", "pages/25_Exec_Client_Summary.py", "📈 Project Summary", {"admin", "exec"}),
    ("Executive Tools", "pages/26_Exec_Project_Summary.py", "⚠️ Risks & Actions", {"admin", "exec"}),
    ("Executive Tools", "pages/27_Bench_Management.py", "👥 Resource Load", {"admin", "exec"}),
    ("Executive Tools", "pages/28_Resource_Allocation_Manager.py", "🧑‍🔧 Resource Allocation Manager", {"admin", "exec"}),

    # --- Admin tools ---
    ("🛠️ Admin Tools", "pages/9_User_Access_Manager.py", "🔐 User Access Manager", {"admin"}),
    ("🛠️ Admin Tools", "pages/11_Project_Setup_Approval.py", "🪪 Project Setup", {"admin"}),
    ("🛠️ Admin Tools", "pages/12_Activity_Log_Viewer.py", "📜 Activity Log Viewer", {"admin"}),
    ("🛠️ Admin Tools", "pages/14_Feedback_Admin.py", "💬 Feedback Manager", {"admin"}),
    ("🛠️ Admin Tools", "pages/20_Admin_Clients.py", "🎛️ Clients Admin", {"admin"}),
    ("🛠️ Admin Tools", "pages/21_Admin_Resource_Pool.py", "🔄 Admin Resource Pool", {"admin"}),
    ("🛠️ Admin Tools","pages/22_RAG_Engine.py", "RAG Engine", {"admin"}),

    # --- Leni ---
    ("🧩 Leni System", "pages/17_OpenAI_Quota_Status.py", "🔋 OpenAI Quota Status", {"admin"}),
    ("🧩 Leni System", "pages/18_Leni_Knowledge_Analytics.py", "💡 Leni Knowledge Analytics", {"admin"}),
    ("🧩 Leni System", "pages/19_Leni_Admin_Console.py", "🧷 Leni Admin Console", {"admin"}),
]
