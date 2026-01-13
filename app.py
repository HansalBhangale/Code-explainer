"""
Repository Intelligence Agent - Enhanced Streamlit Frontend
Beautiful, user-friendly UI with visual graphs and no manual ID entry
"""
import streamlit as st
import requests
import json
from typing import List, Dict, Any
import os
import networkx as nx
import plotly.graph_objects as go

# Page configuration
st.set_page_config(
    page_title="Code Intelligence Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .result-card {
        background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
        border-left: 4px solid #667eea;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    }
    .user-message {
        background: #667eea;
        color: white;
        padding: 12px 18px;
        border-radius: 18px 18px 4px 18px;
        margin: 8px 0;
        max-width: 80%;
        float: right;
        clear: both;
    }
    .assistant-message {
        background: #f0f0f0;
        color: #333;
        padding: 12px 18px;
        border-radius: 18px 18px 18px 4px;
        margin: 8px 0;
        max-width: 80%;
        float: left;
        clear: both;
    }
</style>
""", unsafe_allow_html=True)

# API Configuration
API_BASE = "http://localhost:8000"

# Helper function to create interactive network graph
def create_network_graph(edges_data, title="Network Graph"):
    """Create an interactive network graph using plotly"""
    if not edges_data:
        return None
        
    G = nx.DiGraph()
    
    # Add edges from data
    for edge in edges_data:
        source = edge.get('source', edge.get('src_file', ''))
        target = edge.get('target', edge.get('dst_file', ''))
        if source and target:
            G.add_edge(source, target)
    
    if len(G.nodes()) == 0:
        return None
    
    # Create layout
    pos = nx.spring_layout(G, k=0.5, iterations=50)
    
    # Create edge trace
    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color='#888'),
        hoverinfo='none',
        mode='lines')
    
    # Create node trace
    node_x = []
    node_y = []
    node_text = []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        display_name = node.split('/')[-1] if '/' in node else node
        node_text.append(f"{display_name}<br>In: {G.in_degree(node)} | Out: {G.out_degree(node)}")
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=[n.split('/')[-1] if '/' in n else n for n in G.nodes()],
        textposition="top center",
        hovertext=node_text,
        marker=dict(
            showscale=True,
            colorscale='YlGnBu',
            size=15,
            color=[G.degree(node) for node in G.nodes()],
            colorbar=dict(
                thickness=15,
                title='Connections',
                xanchor='left'
            ),
            line_width=2))
    
    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title=title,
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=0,l=0,r=0,t=40),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        height=600
                    ))
    
    return fig

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'current_snapshot' not in st.session_state:
    st.session_state.current_snapshot = None
if 'current_repo' not in st.session_state:
    st.session_state.current_repo = None
if 'repos' not in st.session_state:
    st.session_state.repos = []
if 'files' not in st.session_state:
    st.session_state.files = []
if 'symbols' not in st.session_state:
    st.session_state.symbols = []

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/000000/artificial-intelligence.png", width=80)
    st.title("🤖 Code Intelligence")
    st.markdown("---")
    
    # Mode selection
    mode = st.selectbox(
        "Select Mode",
        [
            "🏠 Home",
            "📥 Ingestion",
            "📚 Repository Browser",
            "📁 File Explorer",
            "🔗 Import Graph",
            "🌐 API Surface",
            "💬 Chat",
            "🔍 Search",
            "📊 Call Graph",
            "🏷️ Types"
        ]
    )
    
    st.markdown("---")
    
    # Current context display
    if st.session_state.current_repo:
        st.success(f"📦 Repo: {st.session_state.current_repo.get('name', 'Unknown')}")
    if st.session_state.current_snapshot:
        st.success(f"📌 Snapshot: {st.session_state.current_snapshot[:8]}...")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ No snapshot selected")
    
    st.markdown("---")
    st.caption("Built with FastAPI, Neo4j & Gemini AI")

# Main content
st.title("🚀 Repository Intelligence Agent")

# ============================================================================
# HOME
# ============================================================================
if mode == "🏠 Home":
    st.markdown("### Welcome to Code Intelligence Agent!")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("**📥 Ingestion**\nIngest local or GitHub repos")
    with col2:
        st.info("**💬 Chat**\nConverse with your codebase")
    with col3:
        st.info("**🔍 Search**\nHybrid AI-powered search")
    
    st.markdown("---")
    
    # Health check
    if st.button("🏥 Check API Health", use_container_width=True):
        try:
            response = requests.get(f"{API_BASE}/health")
            if response.status_code == 200:
                st.success("✅ API is healthy!")
                data = response.json()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Status", data.get('status', 'unknown'))
                with col2:
                    st.metric("Database", data.get('database', 'unknown'))
            else:
                st.error(f"❌ API unhealthy: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Cannot connect to API: {str(e)}")

# ============================================================================
# INGESTION
# ============================================================================
elif mode == "📥 Ingestion":
    st.markdown("## 📥 Ingest Repository")
    
    tab1, tab2 = st.tabs(["Local Repository", "GitHub Repository"])
    
    with tab1:
        st.markdown("### Ingest Local Repository")
        
        local_path = st.text_input(
            "Repository Path",
            placeholder="C:/path/to/your/repo",
            help="Absolute path to local repository"
        )
        
        if st.button("📂 Ingest Local Repo", use_container_width=True):
            if local_path:
                with st.spinner("🔄 Ingesting repository..."):
                    try:
                        response = requests.post(
                            f"{API_BASE}/api/v1/ingest/local",
                            json={"local_path": local_path}
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            st.success("✅ Ingestion complete!")
                            st.session_state.current_snapshot = data.get('snapshot_id')
                            st.session_state.current_repo = {
                                'repo_id': data.get('repo_id'),
                                'name': data.get('repo_name')
                            }
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Repo", data.get('repo_name', 'N/A'))
                            with col2:
                                st.metric("Status", data.get('status', 'N/A'))
                            with col3:
                                lang_profile = data.get('lang_profile', {})
                                total_files = sum(lang_profile.values()) if lang_profile else 0
                                st.metric("Files", total_files)
                            
                            if lang_profile:
                                st.write("**Language Profile:**")
                                for lang, count in lang_profile.items():
                                    st.write(f"- {lang}: {count} files")
                        else:
                            st.error(f"❌ Error: {response.status_code}")
                            st.code(response.text)
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")
    
    with tab2:
        st.markdown("### Ingest GitHub Repository")
        
        github_url = st.text_input(
            "GitHub URL",
            placeholder="https://github.com/user/repo",
            help="Full GitHub repository URL"
        )
        
        if st.button("🌐 Ingest GitHub Repo", use_container_width=True):
            if github_url:
                with st.spinner("🔄 Cloning and ingesting..."):
                    try:
                        repo_name = github_url.rstrip('/').split('/')[-1]
                        
                        response = requests.post(
                            f"{API_BASE}/api/v1/ingest/git",
                            json={
                                "remote_url": github_url,
                                "repo_name": repo_name
                            }
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            st.success("✅ Ingestion complete!")
                            st.session_state.current_snapshot = data.get('snapshot_id')
                            st.session_state.current_repo = {
                                'repo_id': data.get('repo_id'),
                                'name': data.get('repo_name')
                            }
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Repo", data.get('repo_name', 'N/A'))
                            with col2:
                                st.metric("Status", data.get('status', 'N/A'))
                            with col3:
                                lang_profile = data.get('lang_profile', {})
                                total_files = sum(lang_profile.values()) if lang_profile else 0
                                st.metric("Files", total_files)
                            
                            if lang_profile:
                                st.write("**Language Profile:**")
                                for lang, count in lang_profile.items():
                                    st.write(f"- {lang}: {count} files")
                        else:
                            st.error(f"❌ Error: {response.status_code}")
                            st.code(response.text)
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# REPOSITORY BROWSER
# ============================================================================
elif mode == "📚 Repository Browser":
    st.markdown("## 📚 Repository Browser")
    
    # Load repos
    if st.button("🔄 Refresh Repositories", use_container_width=True):
        try:
            response = requests.get(f"{API_BASE}/api/v1/repos")
            if response.status_code == 200:
                st.session_state.repos = response.json()
                st.success(f"Found {len(st.session_state.repos)} repositories")
            else:
                st.error(f"❌ Error: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Failed: {str(e)}")
    
    if st.session_state.repos:
        st.markdown("### Select a Repository")
        
        for repo in st.session_state.repos:
            with st.expander(f"📦 {repo['name']}", expanded=False):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Type:** {repo.get('source_type', 'unknown')}")
                    st.write(f"**Created:** {repo.get('created_at', 'N/A')}")
                    if repo.get('remote_url'):
                        st.write(f"**URL:** {repo['remote_url']}")
                
                with col2:
                    if st.button("Select", key=f"select_repo_{repo['repo_id']}", use_container_width=True):
                        st.session_state.current_repo = repo
                        # Clear chat history when switching repos
                        st.session_state.chat_history = []
                        # Load snapshots for this repo
                        try:
                            snap_response = requests.get(f"{API_BASE}/api/v1/repos/{repo['repo_id']}/snapshots")
                            if snap_response.status_code == 200:
                                snapshots = snap_response.json()
                                if snapshots:
                                    # Auto-select latest snapshot
                                    st.session_state.current_snapshot = snapshots[0]['snapshot_id']
                                    st.success(f"✅ Selected {repo['name']} with latest snapshot")
                                    st.info(f"📌 Snapshot: {snapshots[0]['snapshot_id'][:16]}...")
                                    st.rerun()
                        except:
                            pass
                
                # Show snapshots if this repo is selected
                if st.session_state.current_repo and st.session_state.current_repo['repo_id'] == repo['repo_id']:
                    try:
                        snap_response = requests.get(f"{API_BASE}/api/v1/repos/{repo['repo_id']}/snapshots")
                        if snap_response.status_code == 200:
                            snapshots = snap_response.json()
                            if snapshots:
                                st.markdown("**Available Snapshots:**")
                                for snap in snapshots:
                                    is_current = snap['snapshot_id'] == st.session_state.current_snapshot
                                    snap_label = f"{'✅ ' if is_current else ''}Snapshot {snap['snapshot_id'][:8]}... ({snap.get('status', 'unknown')})"
                                    if st.button(snap_label, key=f"snap_{snap['snapshot_id']}", disabled=is_current):
                                        st.session_state.current_snapshot = snap['snapshot_id']
                                        st.rerun()
                    except:
                        pass

# ============================================================================
# FILE EXPLORER
# ============================================================================
elif mode == "📁 File Explorer":
    st.markdown("## 📁 File Explorer")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        if st.button("📄 Load Files", use_container_width=True):
            try:
                response = requests.get(
                    f"{API_BASE}/api/v1/snapshots/{st.session_state.current_snapshot}/files"
                )
                if response.status_code == 200:
                    st.session_state.files = response.json()
                    st.success(f"Found {len(st.session_state.files)} files")
                else:
                    st.error(f"❌ Error: {response.status_code}")
            except Exception as e:
                st.error(f"❌ Failed: {str(e)}")
        
        if st.session_state.files:
            # Group files by language
            files_by_lang = {}
            for file in st.session_state.files:
                lang = file.get('language', 'unknown')
                if lang not in files_by_lang:
                    files_by_lang[lang] = []
                files_by_lang[lang].append(file)
            
            # Display by language
            for lang, files in files_by_lang.items():
                with st.expander(f"📚 {lang.upper()} ({len(files)} files)", expanded=True):
                    for file in files:
                        col1, col2, col3 = st.columns([4, 1, 1])
                        with col1:
                            st.write(f"📄 `{file['path']}`")
                        with col2:
                            st.caption(f"{file['loc']} lines")
                        with col3:
                            if file['is_test']:
                                st.caption("🧪 Test")

# ============================================================================
# IMPORT GRAPH
# ============================================================================
elif mode == "🔗 Import Graph":
    st.markdown("## 🔗 Import Dependency Graph")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        if st.button("🌐 Generate Import Graph", use_container_width=True):
            with st.spinner("Loading import graph..."):
                try:
                    response = requests.get(
                        f"{API_BASE}/api/v1/snapshots/{st.session_state.current_snapshot}/import-graph"
                    )
                    if response.status_code == 200:
                        data = response.json()
                        edges = data.get('edges', [])
                        
                        if edges:
                            st.success(f"Found {len(edges)} import relationships")
                            
                            # Create and display graph
                            fig = create_network_graph(edges, "Import Dependency Graph")
                            if fig:
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Show statistics
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Total Imports", len(edges))
                                with col2:
                                    unique_sources = len(set(e.get('source', e.get('src_file', '')) for e in edges))
                                    st.metric("Files Importing", unique_sources)
                                with col3:
                                    unique_targets = len(set(e.get('target', e.get('dst_file', '')) for e in edges))
                                    st.metric("Files Imported", unique_targets)
                            else:
                                st.warning("No graph data to display")
                        else:
                            st.info("No import relationships found")
                    else:
                        st.error(f"❌ Error: {response.status_code}")
                except Exception as e:
                    st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# CHAT
# ============================================================================
elif mode == "💬 Chat":
    st.markdown("## 💬 Conversational Code Explorer")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        # Show current context and clear button
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.session_state.current_repo:
                st.info(f"🗂️ **Current Repository:** {st.session_state.current_repo.get('name', 'Unknown')} | **Snapshot:** {st.session_state.current_snapshot[:16]}...")
        with col2:
            if st.button("🗑️ Clear Chat"):
                st.session_state.chat_history = []
                st.rerun()
        
        # Chat container
        for msg in st.session_state.chat_history:
            if msg['role'] == 'user':
                st.markdown(f'<div class="user-message">👤 {msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="assistant-message">🤖 {msg["content"]}</div>', unsafe_allow_html=True)
                
                if 'chunks' in msg and msg['chunks']:
                    with st.expander(f"📄 Retrieved {len(msg['chunks'])} code snippets"):
                        for i, chunk in enumerate(msg['chunks'], 1):
                            st.markdown(f"**{i}. {chunk['symbol_name']}** ({chunk['symbol_kind']})")
                            st.code(chunk['content'][:300] + "...", language="python")
        
        # Chat input
        st.markdown("---")
        col1, col2 = st.columns([6, 1])
        
        with col1:
            user_input = st.text_input("Ask me anything...", key="chat_input")
        
        with col2:
            if st.button("Send 📤"):
                if user_input:
                    st.session_state.chat_history.append({"role": "user", "content": user_input})
                    
                    with st.spinner("🤔 Thinking..."):
                        try:
                            history = [{"role": m["role"], "content": m["content"]} 
                                      for m in st.session_state.chat_history[:-1]]
                            
                            response = requests.post(
                                f"{API_BASE}/api/v1/chat/message",
                                json={
                                    "query": user_input,
                                    "snapshot_id": st.session_state.current_snapshot,
                                    "conversation_history": history,
                                    "top_k": 3
                                }
                            )
                            
                            if response.status_code == 200:
                                data = response.json()
                                st.session_state.chat_history.append({
                                    "role": "assistant",
                                    "content": data['answer'],
                                    "chunks": data.get('retrieved_chunks', [])
                                })
                                st.rerun()
                            else:
                                st.error(f"❌ Error: {response.status_code}")
                        except Exception as e:
                            st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# SEARCH
# ============================================================================
elif mode == "🔍 Search":
    st.markdown("## 🔍 Hybrid Code Search")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        search_query = st.text_input("Search for code...", key="search_input")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            explain = st.checkbox("AI Explanations", value=True)
        with col2:
            top_k = st.slider("Results", 1, 10, 5)
        with col3:
            explain_top_n = st.slider("Explain top", 1, 5, 3)
        
        if st.button("Search 🔎", use_container_width=True):
            if search_query:
                with st.spinner("🔍 Searching..."):
                    try:
                        endpoint = "/api/v1/rag/search/explain" if explain else "/api/v1/rag/search"
                        
                        payload = {
                            "query": search_query,
                            "snapshot_id": st.session_state.current_snapshot,
                            "top_k": top_k,
                            "lexical_weight": 0.3,
                            "vector_weight": 0.5,
                            "graph_weight": 0.2,
                            "expand_graph": True
                        }
                        
                        if explain:
                            payload["explain"] = True
                            payload["explain_top_n"] = explain_top_n
                        
                        response = requests.post(f"{API_BASE}{endpoint}", json=payload)
                        
                        if response.status_code == 200:
                            results = response.json()
                            st.success(f"✅ Found {results['total_results']} results!")
                            
                            for i, result in enumerate(results['results'], 1):
                                st.markdown(f'<div class="result-card">', unsafe_allow_html=True)
                                st.markdown(f"**{i}. {result['symbol_name']}** `{result['symbol_kind']}`")
                                st.caption(f"📁 {result['file_path']} | Score: {result['final_score']:.4f}")
                                
                                if 'explanation' in result and result['explanation']:
                                    st.info(result['explanation'])
                                
                                with st.expander("📄 View Code"):
                                    st.code(result['content'], language="python")
                                
                                st.markdown('</div>', unsafe_allow_html=True)
                        else:
                            st.error(f"❌ Error: {response.status_code}")
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# API SURFACE
# ============================================================================
elif mode == "🌐 API Surface":
    st.markdown("## 🌐 API Surface Map")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        # Add filter toggle
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("📋 Load API Endpoints", use_container_width=True):
                st.session_state.load_endpoints = True
        with col2:
            show_all = st.checkbox("Show All", help="Include test files and examples")
        
        if st.session_state.get('load_endpoints', False):
            try:
                response = requests.get(
                    f"{API_BASE}/api/v1/snapshots/{st.session_state.current_snapshot}/api-surface"
                )
                if response.status_code == 200:
                    data = response.json()
                    all_endpoints = data.get('endpoints', [])
                    
                    # Apply filtering based on toggle
                    if show_all:
                        # Show all endpoints
                        main_endpoints = all_endpoints
                        st.info(f"ℹ️ Showing all {len(all_endpoints)} endpoints (including tests and examples)")
                    else:
                        # Filter to show only main project API endpoints
                        main_endpoints = []
                        for ep in all_endpoints:
                            path = ep.get('path', '')
                            
                            # Only show endpoints that start with /api/v1/ (main project APIs)
                            if path.startswith('/api/v1/') or path.startswith('/health'):
                                main_endpoints.append(ep)
                        
                        # If no /api/v1/ endpoints, try /api/ prefix
                        if not main_endpoints:
                            for ep in all_endpoints:
                                path = ep.get('path', '')
                                if path.startswith('/api/'):
                                    main_endpoints.append(ep)
                        
                        # If still nothing, show all with warning
                        if not main_endpoints:
                            main_endpoints = all_endpoints
                            st.warning("⚠️ No /api/* endpoints found. Showing all endpoints. Check 'Show All' to confirm.")
                        else:
                            filtered_count = len(all_endpoints) - len(main_endpoints)
                            if filtered_count > 0:
                                st.info(f"ℹ️ Showing {len(main_endpoints)} main API endpoints (filtered out {filtered_count} test/example endpoints)")
                    
                    st.success(f"Found {len(main_endpoints)} API endpoints")
                    
                    # Group by HTTP method
                    by_method = {}
                    for ep in main_endpoints:
                        method = ep.get('http_method', 'UNKNOWN')
                        if method not in by_method:
                            by_method[method] = []
                        by_method[method].append(ep)
                    
                    # Display by method
                    for method, eps in by_method.items():
                        method_colors = {
                            "GET": "🟢",
                            "POST": "🟡",
                            "PUT": "🔵",
                            "DELETE": "🔴",
                            "PATCH": "🟠"
                        }
                        
                        with st.expander(f"{method_colors.get(method, '⚪')} {method} ({len(eps)} endpoints)", expanded=True):
                            for ep in eps:
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    # Show the actual path
                                    path = ep.get('path', 'N/A')
                                    st.write(f"**`{path}`**")
                                    if ep.get('summary'):
                                        st.caption(ep['summary'])
                                    elif ep.get('description'):
                                        st.caption(ep['description'][:100] + "..." if len(ep.get('description', '')) > 100 else ep.get('description', ''))
                                with col2:
                                    if ep.get('response_model'):
                                        st.caption(f"→ {ep['response_model']}")
                                    if ep.get('deprecated'):
                                        st.warning("⚠️ Deprecated")
                else:
                    st.error(f"❌ Error: {response.status_code}")
            except Exception as e:
                st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# CALL GRAPH
# ============================================================================
elif mode == "📊 Call Graph":
    st.markdown("## 📊 Call Graph Explorer")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        # First, let user select a file to explore
        if st.button("📄 Load Files for Call Graph", use_container_width=True):
            try:
                response = requests.get(
                    f"{API_BASE}/api/v1/snapshots/{st.session_state.current_snapshot}/files"
                )
                if response.status_code == 200:
                    st.session_state.files = response.json()
                    st.success(f"Loaded {len(st.session_state.files)} files")
            except Exception as e:
                st.error(f"❌ Failed: {str(e)}")
        
        if st.session_state.files:
            # Let user select a file
            file_options = {f"{f['path']}": f['file_id'] for f in st.session_state.files}
            selected_file = st.selectbox("Select a file to explore", options=list(file_options.keys()))
            
            if selected_file:
                file_id = file_options[selected_file]
                st.caption(f"File ID: `{file_id[:16]}...`")  # Debug: show file_id
                
                # Show both callees and callers
                tab1, tab2 = st.tabs(["📤 Imports (Callees)", "📥 Imported By (Callers)"])
                
                with tab1:
                    st.caption("Files that this file imports")
                    if st.button("🔍 Get File Imports", use_container_width=True, key=f"imports_{file_id}"):
                        try:
                            # Get file imports (file-to-file relationships)
                            response = requests.get(f"{API_BASE}/api/v1/files/{file_id}/imports")
                            if response.status_code == 200:
                                data = response.json()
                                
                                # The API returns files that this file imports (file-to-file relationships)
                                imports = data.get('imports', [])
                                if imports:
                                    st.success(f"This file imports {len(imports)} other files")
                                    
                                    for imp in imports:
                                        file_path = imp.get('path', 'Unknown')
                                        imported_file_id = imp.get('file_id', '')
                                        st.write(f"- 📄 `{file_path}`")
                                        if imported_file_id:
                                            st.caption(f"   File ID: {imported_file_id[:16]}...")
                                else:
                                    st.info("This file doesn't import any other files in the codebase")
                                    st.caption("Note: External package imports (like numpy, pandas) are not shown here")
                            else:
                                st.error(f"❌ Error: {response.status_code}")
                        except Exception as e:
                            st.error(f"❌ Failed: {str(e)}")
                
                with tab2:
                    st.caption("Files that import this file")
                    if st.button("🔍 Get Reverse Dependencies", use_container_width=True, key=f"reverse_{file_id}"):
                        try:
                            # Get reverse dependencies using file path
                            response = requests.get(
                                f"{API_BASE}/api/v1/snapshots/{st.session_state.current_snapshot}/dependencies/{selected_file}"
                            )
                            if response.status_code == 200:
                                data = response.json()
                                dependents = data.get('dependent_files', [])  # Fixed: use 'dependent_files'
                                
                                if dependents:
                                    st.success(f"Found {len(dependents)} files that import this file")
                                    
                                    for dep in dependents:
                                        dep_path = dep.get('file_path', 'Unknown')
                                        dep_file_id = dep.get('file_id', '')
                                        st.write(f"- 📄 `{dep_path}`")
                                        if dep_file_id:
                                            st.caption(f"   File ID: {dep_file_id[:16]}...")
                                else:
                                    st.info("No files import this file")
                            else:
                                st.error(f"❌ Error: {response.status_code}")
                        except Exception as e:
                            st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# TYPES
# ============================================================================
elif mode == "🏷️ Types":
    st.markdown("## 🏷️ Type Annotations Explorer")
    
    if not st.session_state.current_snapshot:
        st.warning("⚠️ Please select a repository and snapshot first")
    else:
        tab1, tab2 = st.tabs(["🔍 Search Types", "📊 Type Statistics"])
        
        with tab1:
            st.markdown("### Search for Type Patterns")
            
            pattern = st.text_input(
                "Type Pattern",
                placeholder="e.g., Dict, List, Optional, str",
                help="Search for type annotations containing this pattern"
            )
            
            if st.button("🔍 Search Types", use_container_width=True):
                if pattern:
                    try:
                        response = requests.get(
                            f"{API_BASE}/api/v1/types/search",
                            params={
                                "pattern": pattern,
                                "snapshot_id": st.session_state.current_snapshot
                            }
                        )
                        if response.status_code == 200:
                            results = response.json()
                            
                            if isinstance(results, list) and results:
                                st.success(f"Found {len(results)} type annotations")
                                
                                for i, result in enumerate(results[:20], 1):  # Show first 20
                                    with st.expander(f"{i}. {result.get('symbol_name', 'Unknown')}"):
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.write(f"**Type:** `{result.get('type_annotation', 'N/A')}`")
                                            st.write(f"**Kind:** {result.get('annotation_kind', 'N/A')}")
                                        with col2:
                                            st.write(f"**File:** `{result.get('file_path', 'N/A')}`")
                                            st.write(f"**Line:** {result.get('line_number', 'N/A')}")
                            else:
                                st.info("No type annotations found matching this pattern")
                        elif response.status_code == 404:
                            st.warning("⚠️ Type search endpoint not available")
                        else:
                            st.error(f"❌ Error: {response.status_code}")
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")
                else:
                    st.warning("Please enter a type pattern to search")
        
        with tab2:
            st.markdown("### Type Statistics")
            
            if st.button("📊 Get Type Stats", use_container_width=True):
                try:
                    # Correct endpoint path
                    response = requests.get(
                        f"{API_BASE}/api/v1/types/snapshots/{st.session_state.current_snapshot}/type-stats"
                    )
                    if response.status_code == 200:
                        stats = response.json()
                        
                        # Display statistics
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Total Types", stats.get('total_types', 0))
                        with col2:
                            st.metric("Unique Types", stats.get('unique_types', 0))
                        with col3:
                            st.metric("Files with Types", stats.get('files_with_types', 0))
                        
                        # Show common types if available
                        if 'common_types' in stats and stats['common_types']:
                            st.markdown("---")
                            st.markdown("**Most Common Types:**")
                            for type_info in stats['common_types'][:10]:
                                st.write(f"- `{type_info.get('type', 'N/A')}`: {type_info.get('count', 0)} occurrences")
                    else:
                        st.error(f"❌ Error: {response.status_code}")
                except Exception as e:
                    st.error(f"❌ Failed: {str(e)}")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p>🤖 <strong>Repository Intelligence Agent</strong></p>
</div>
""", unsafe_allow_html=True)
