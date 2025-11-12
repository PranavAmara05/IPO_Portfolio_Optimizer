import os
import re
from datetime import datetime, date
from pymongo import MongoClient
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------- CONFIG ----------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "ipo_db"
COL_IPOS = "ipos"
COL_ANALYSIS = "ipo_analysis"
COL_RECOMMEND = "ipo_portfolio_recommendations"

MIN_INVEST_MAINBOARD = 15000
DEFAULT_MAX_LOTS_PER_IPO = 3
DIVERSIFICATION_WEIGHT = 0.10
TOP_FILL_K = 3

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="IPO Portfolio Allocator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- CUSTOM CSS ----------
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(120deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        font-size: 1.2rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .ipo-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin-bottom: 1rem;
    }
    .score-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .score-high { background: #10b981; color: white; }
    .score-medium { background: #f59e0b; color: white; }
    .score-low { background: #ef4444; color: white; }
    .stButton>button {
        background: linear-gradient(120deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        font-weight: 600;
        border-radius: 8px;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ---------- UTILITIES ----------
def safe_float(x):
    try:
        return float(str(x).replace("₹", "").replace(",", "").strip())
    except Exception:
        return None

def try_parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    fmts = ["%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s[:len(f)], f).date()
        except Exception:
            pass
    try:
        import dateutil.parser
        return dateutil.parser.parse(s, dayfirst=True).date()
    except Exception:
        return None

def parse_lot_and_min_invest(text):
    if not text:
        return None, None
    s = str(text)
    m = re.search(r"(?:Min[:\s]*)?(\d{1,6})\s*shares?.*?₹\s?([\d,]+)", s, flags=re.I)
    if m:
        lot = safe_float(m.group(1))
        min_inv = safe_float(m.group(2))
        return int(lot) if lot else None, float(min_inv) if min_inv else None
    m2 = re.search(r"₹\s?([\d,]+)", s)
    if m2:
        return None, float(safe_float(m2.group(1)))
    return None, None

def parse_issue_mid(ipo_doc):
    v = ipo_doc.get("issue_price") or ipo_doc.get("extracted_fields", {}).get("Price Band")
    if isinstance(v, dict):
        mid = v.get("avg") or v.get("mid") or v.get("min")
        return safe_float(mid)
    if not v:
        return None
    nums = re.findall(r"\d+\.?\d*", str(v))
    nums = [safe_float(n) for n in nums if safe_float(n) is not None]
    return sum(nums)/len(nums) if nums else None

def sanitize_for_mongo(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_mongo(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_mongo(x) for x in obj]
    elif isinstance(obj, date):
        return datetime(obj.year, obj.month, obj.day).isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

# ---------- SCORING COMPONENTS ----------
def extract_retail_quota(text):
    if not text:
        return 10.0
    m = re.search(r"Retail\s*:?(\d+\.?\d*)%", str(text), flags=re.I)
    if m:
        return safe_float(m.group(1))
    return 10.0

def extract_fundamental_score(text):
    if not text:
        return 5.0
    score = 5.0
    t = str(text).lower()
    if "profit" in t or "positive" in t or "growth" in t:
        score += 2
    if "loss" in t or "negative" in t:
        score -= 2
    m = re.search(r"roe[:\s]*([-\d.]+)", t)
    if m:
        roe = safe_float(m.group(1))
        if roe and roe > 10:
            score += 1.5
    m = re.search(r"d/?e[:\s]*([-\d.]+)", t)
    if m:
        de = safe_float(m.group(1))
        if de and de > 1:
            score -= 1
    m = re.search(r"eps[:\s]*[-(₹]?([\d.]+)", t)
    if m:
        eps = safe_float(m.group(1))
        if eps and eps > 0:
            score += 1
        else:
            score -= 1
    return max(1, min(score, 10))

def extract_sentiment(text):
    if not text:
        return 5.0
    t = str(text).lower()
    score = 5.0
    good = ["growing", "leader", "expanding", "innovative", "strong", "profitable", "stable"]
    bad = ["loss", "decline", "volatile", "uncertain", "risky", "unprofitable"]
    for w in good:
        if w in t:
            score += 0.5
    for w in bad:
        if w in t:
            score -= 0.5
    return max(1, min(score, 10))

def compute_composite_and_breakdown(ipo_doc, analysis):
    fields = ipo_doc.get("extracted_fields", {}) or {}
    base = analysis.get("score", 5)
    retail = extract_retail_quota(fields.get("Investor Quota Split"))
    fund = extract_fundamental_score(fields.get("Valuation Ratios (EPS, ROE, ROCE, D/E, NAV)") or fields.get("Financial Performance (FY23–FY25)"))
    sent = extract_sentiment(fields.get("Company Overview"))
    gmp = safe_float(ipo_doc.get("gmp_investorgain")) or 0
    issue = parse_issue_mid(ipo_doc)
    gmp_strength = (gmp / issue * 100) if (gmp and issue) else 0
    rq_score = min(retail / 10, 1) * 10

    w_base = 0.30
    w_rq = 0.25
    w_fund = 0.20
    w_gmp = 0.15
    w_sent = 0.10

    composite = w_base*base + w_rq*rq_score + w_fund*fund + w_gmp*(gmp_strength/10) + w_sent*sent
    composite = round(min(composite, 10), 3)

    breakdown = {
        "base_score": base,
        "retail_quota_pct": retail,
        "rq_score": round(rq_score,3),
        "fund_score": round(fund,3),
        "sentiment_score": round(sent,3),
        "gmp_strength_pct": round(gmp_strength,3),
        "weights": {"base": w_base, "retail": w_rq, "fund": w_fund, "gmp": w_gmp, "sentiment": w_sent}
    }
    return composite, breakdown

# ---------- DATA LOAD ----------
@st.cache_data(ttl=300)
def load_data():
    client = MongoClient(MONGO_URI)
    ipos = list(client[DB_NAME][COL_IPOS].find({}))
    analysis = list(client[DB_NAME][COL_ANALYSIS].find({}))
    client.close()
    ipos_by_name = {d["ipo"]: d for d in ipos if "ipo" in d}
    scored = {a["ipo"]: a for a in analysis if "ipo" in a}
    return ipos_by_name, scored

# ---------- BUILD CANDIDATES ----------
def build_candidates(ipos_by_name, scored, hold_date):
    cands = []
    for name, ipo in ipos_by_name.items():
        if name not in scored:
            continue
        analysis = scored[name]
        if analysis.get("status") != "scored" and "score" not in analysis:
            continue
        fields = ipo.get("extracted_fields", {}) or {}
        close = ipo.get("close_date") or fields.get("IPO Dates") or fields.get("Close Date")
        close_date = try_parse_date(str(close))
        if not close_date or close_date > hold_date:
            continue

        issue_mid = parse_issue_mid(ipo)
        if not issue_mid:
            continue

        lot, min_inv = parse_lot_and_min_invest(fields.get("Market Lot & Amounts"))
        if not min_inv:
            min_inv = (lot * issue_mid) if lot else MIN_INVEST_MAINBOARD

        composite, breakdown = compute_composite_and_breakdown(ipo, analysis)
        if composite < 5:
            continue

        cands.append({
            "ipo": name,
            "category": ipo.get("category", "Mainboard"),
            "composite": composite,
            "breakdown": breakdown,
            "issue_mid": issue_mid,
            "lot": int(lot) if lot else None,
            "min_invest": float(min_inv),
            "close_date": close_date,
            "gmp_investorgain": ipo.get("gmp_investorgain"),
            "analysis": analysis
        })
    return cands

# ---------- GREEDY-FILL ----------
def greedy_fill_full(candidates, budget):
    candidates = sorted(candidates, key=lambda x: x["composite"]/x["min_invest"], reverse=True)
    allocation = []
    remaining = budget
    min_unit = min(c["min_invest"] for c in candidates)

    for c in candidates:
        if remaining >= c["min_invest"]:
            allocation.append({"ipo": c["ipo"], "lots": 1, "min_invest": c["min_invest"], "invested": c["min_invest"], "composite": c["composite"]})
            remaining -= c["min_invest"]

    top_k = candidates[:min(TOP_FILL_K, len(candidates))]
    added = True
    while added and remaining >= min_unit:
        added = False
        for c in top_k:
            if remaining >= c["min_invest"]:
                found = next((a for a in allocation if a["ipo"] == c["ipo"]), None)
                if found:
                    found["lots"] += 1
                    found["invested"] += c["min_invest"]
                else:
                    allocation.append({"ipo": c["ipo"], "lots": 1, "min_invest": c["min_invest"], "invested": c["min_invest"], "composite": c["composite"]})
                remaining -= c["min_invest"]
                added = True
            if remaining < min_unit:
                break

    while remaining >= min_unit:
        affordable = [c for c in candidates if c["min_invest"] <= remaining]
        if not affordable:
            break
        pick = max(affordable, key=lambda x: x["composite"]/x["min_invest"])
        found = next((a for a in allocation if a["ipo"] == pick["ipo"]), None)
        if found:
            found["lots"] += 1
            found["invested"] += pick["min_invest"]
        else:
            allocation.append({"ipo": pick["ipo"], "lots": 1, "min_invest": pick["min_invest"], "invested": pick["min_invest"], "composite": pick["composite"]})
        remaining -= pick["min_invest"]

    allocation = sorted(allocation, key=lambda x: x["composite"], reverse=True)
    return allocation, remaining

# ---------- MILP ----------
def allocate_balanced(candidates, budget):
    try:
        import pulp
    except ImportError:
        return None, None

    prob = pulp.LpProblem("Balanced_IPO", pulp.LpMaximize)
    vars_map = {}
    for c in candidates:
        safe_name = re.sub(r"\W+", "_", c["ipo"])
        max_possible = int(max(1, budget // c["min_invest"]))
        cap = min(DEFAULT_MAX_LOTS_PER_IPO, max_possible)
        vars_map[c["ipo"]] = pulp.LpVariable(f"lots_{safe_name}", lowBound=0, upBound=cap, cat="Integer")

    # Objective: maximize composite score with diversification
    # Since PuLP is linear, we use a simple penalty: penalize total lots allocated
    # This encourages spreading across IPOs rather than concentrating
    obj = pulp.lpSum([c["composite"] * vars_map[c["ipo"]] for c in candidates])
    
    # Linear diversification: slightly penalize total number of lots
    # This encourages the solver to prefer fewer lots per IPO (via the cap) and more IPOs
    total_lots = pulp.lpSum([vars_map[c["ipo"]] for c in candidates])
    
    prob += obj - (DIVERSIFICATION_WEIGHT * total_lots)
    
    # Budget constraint
    prob += pulp.lpSum([c["min_invest"] * vars_map[c["ipo"]] for c in candidates]) <= budget

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))

    allocation = []
    total_invested = 0.0
    for c in candidates:
        v = int(pulp.value(vars_map[c["ipo"]]) or 0)
        if v > 0:
            invested = v * c["min_invest"]
            allocation.append({"ipo": c["ipo"], "lots": v, "invested": invested, "min_invest": c["min_invest"], "composite": c["composite"]})
            total_invested += invested
    remaining = budget - total_invested
    return allocation, remaining

# ---------- EXPLAINABILITY ----------
def explain_allocation(allocation, candidates_dict):
    explain = {}
    for a in allocation:
        c = candidates_dict.get(a["ipo"])
        reasons_more = []
        reasons_less = []
        br = c["breakdown"]
        reasons_more.append(f"Composite score {c['composite']} computed from base_score={br['base_score']}, retail_q={br['retail_quota_pct']}%, fund={br['fund_score']}, sentiment={br['sentiment_score']}, gmp_str={br['gmp_strength_pct']}%")
        if br['gmp_strength_pct'] > 10:
            reasons_more.append(f"High GMP strength {br['gmp_strength_pct']}% → strong listing expectation")
        if br['retail_quota_pct'] >= 30:
            reasons_more.append("High retail quota → better allotment odds")
        else:
            reasons_less.append(f"Retail quota {br['retail_quota_pct']}% is low")
        if br['fund_score'] >= 6:
            reasons_more.append("Fundamentals show positive indicators")
        else:
            reasons_less.append("Fundamentals are weak/moderate")
        if "sme" in str(c.get("category","")).lower():
            reasons_less.append("SME IPO: higher risk & lower liquidity")
        explain[a["ipo"]] = {"reasons_more": reasons_more, "reasons_less": reasons_less, "breakdown": br}
    return explain

def get_score_class(score):
    if score >= 7:
        return "score-high"
    elif score >= 5:
        return "score-medium"
    else:
        return "score-low"

# ---------- MAIN APP ----------
def main():
    # Header
    st.markdown('<h1 class="main-header">📊 IPO Portfolio Allocator</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Intelligent allocation engine with AI-powered scoring</p>', unsafe_allow_html=True)
    
    # Sidebar inputs
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/000000/investment-portfolio.png", width=80)
        st.header("⚙️ Configuration")
        
        budget = st.number_input(
            "💰 Total Budget (₹)",
            min_value=10000,
            max_value=10000000,
            value=100000,
            step=10000,
            help="Enter your total investment budget"
        )
        
        hold_date = st.date_input(
            "📅 Hold Until Date",
            value=datetime.now().date(),
            help="Select the date until which you want to hold the IPO"
        )
        
        st.divider()
        
        st.subheader("🎛️ Algorithm Parameters")
        with st.expander("Advanced Settings", expanded=False):
            st.info(f"""
            - **Min Invest (Mainboard):** ₹{MIN_INVEST_MAINBOARD:,}
            - **Max Lots per IPO:** {DEFAULT_MAX_LOTS_PER_IPO}
            - **Diversification Weight:** {DIVERSIFICATION_WEIGHT}
            - **Top Fill K:** {TOP_FILL_K}
            """)
        
        run_analysis = st.button("🚀 Run Analysis", use_container_width=True)
    
    # Main content
    if run_analysis:
        with st.spinner("🔄 Loading data from MongoDB..."):
            try:
                ipos_by_name, scored = load_data()
                candidates = build_candidates(ipos_by_name, scored, hold_date)
            except Exception as e:
                st.error(f"❌ Error loading data: {str(e)}")
                return
        
        if not candidates:
            st.warning("⚠️ No eligible IPOs found (score >=5 & within hold date)")
            return
        
        # Display eligible IPOs
        st.success(f"✅ Found {len(candidates)} eligible IPOs")
        
        with st.expander("📋 View All Eligible IPOs", expanded=False):
            df_candidates = pd.DataFrame([{
                "IPO": c["ipo"],
                "Category": c["category"],
                "Composite Score": c["composite"],
                "Min Investment": f"₹{int(c['min_invest']):,}",
                "Retail Quota": f"{c['breakdown']['retail_quota_pct']}%",
                "GMP Strength": f"{c['breakdown']['gmp_strength_pct']:.1f}%"
            } for c in candidates])
            st.dataframe(df_candidates, use_container_width=True)
        
        # Run allocation
        with st.spinner("🧮 Computing optimal allocation..."):
            allocation, remaining = allocate_balanced(candidates, budget)
            if allocation is None:
                st.info("⚠️ PuLP not installed — using greedy algorithm")
                allocation, remaining = greedy_fill_full(candidates, budget)
            else:
                if remaining > 0.01 * budget:
                    g_alloc, g_rem = greedy_fill_full(candidates, budget)
                    if (budget - g_rem) > (budget - remaining):
                        allocation, remaining = g_alloc, g_rem
        
        total_invested = sum(a["invested"] for a in allocation)
        
        # Results metrics
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💼 Total Budget", f"₹{int(budget):,}")
        with col2:
            st.metric("💵 Total Invested", f"₹{int(total_invested):,}")
        with col3:
            st.metric("💤 Remaining", f"₹{int(remaining):,}")
        with col4:
            utilization = (total_invested / budget) * 100
            st.metric("📊 Utilization", f"{utilization:.1f}%")
        
        # Allocation visualization
        st.divider()
        st.subheader("📈 Allocation Breakdown")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Pie chart
            fig_pie = go.Figure(data=[go.Pie(
                labels=[a["ipo"] for a in allocation],
                values=[a["invested"] for a in allocation],
                hole=0.4,
                marker_colors=px.colors.sequential.Plasma
            )])
            fig_pie.update_layout(
                title="Investment Distribution",
                height=400,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Bar chart for scores
            fig_bar = go.Figure(data=[go.Bar(
                x=[a["composite"] for a in allocation],
                y=[a["ipo"] for a in allocation],
                orientation='h',
                marker_color=px.colors.sequential.Viridis
            )])
            fig_bar.update_layout(
                title="Composite Scores",
                xaxis_title="Score",
                yaxis_title="IPO",
                height=400
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Detailed allocation table
        st.divider()
        st.subheader("📊 Detailed Allocation Plan")
        
        df_allocation = pd.DataFrame([{
            "IPO Name": a["ipo"],
            "Lots": a["lots"],
            "Amount Invested": f"₹{int(a['invested']):,}",
            "Min Unit": f"₹{int(a['min_invest']):,}",
            "Composite Score": a["composite"]
        } for a in allocation])
        
        st.dataframe(df_allocation, use_container_width=True, height=300)
        
        # Explainability section
        st.divider()
        st.subheader("🔍 Investment Analysis & Explainability")
        
        candidates_dict = {c["ipo"]: c for c in candidates}
        explain = explain_allocation(allocation, candidates_dict)
        
        for ipo, info in explain.items():
            with st.expander(f"📌 {ipo}", expanded=False):
                br = info["breakdown"]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Base Score", f"{br['base_score']:.1f}")
                with col2:
                    st.metric("Retail Quota", f"{br['retail_quota_pct']:.1f}%")
                with col3:
                    st.metric("GMP Strength", f"{br['gmp_strength_pct']:.1f}%")
                
                col4, col5 = st.columns(2)
                with col4:
                    st.metric("Fund Score", f"{br['fund_score']:.1f}")
                with col5:
                    st.metric("Sentiment", f"{br['sentiment_score']:.1f}")
                
                st.divider()
                
                if info["reasons_more"]:
                    st.success("✅ **Positive Factors:**")
                    for r in info["reasons_more"]:
                        st.write(f"• {r}")
                
                if info["reasons_less"]:
                    st.warning("⚠️ **Caution Factors:**")
                    for r in info["reasons_less"]:
                        st.write(f"• {r}")
        
        # Algorithm explanation
        st.divider()
        st.subheader("🧠 Algorithm & Formula")
        
        with st.expander("📖 How It Works", expanded=False):
            st.markdown("""
            ### Composite Score Formula
            ```
            composite = 0.30×base_score + 0.25×rq_score + 0.20×fund_score 
                       + 0.15×(gmp_strength/10) + 0.10×sentiment_score
            ```
            
            Where:
            - **rq_score** = min(retail_pct/10, 1) × 10 (normalized 0-10)
            - **base_score** = Initial analysis score
            - **fund_score** = Fundamental indicators (EPS, ROE, D/E)
            - **sentiment_score** = Business sentiment analysis
            - **gmp_strength** = Grey market premium strength percentage
            
            ### Allocation Strategy
            1. **MILP Optimization** (if PuLP available):
               - Maximizes: Σ(composite × lots) - 0.10 × Σ(lots²)
               - Diversification penalty prevents over-concentration
            
            2. **Greedy Fallback**:
               - Round 1: Allocate 1 lot to top candidates
               - Round 2: Fill top-K repeatedly (round-robin)
               - Round 3: Use remaining budget on best candidates
            
            ### Filtering
            - Only IPOs with composite score ≥ 5
            - Close date must be before hold-until date
            - Must have valid pricing and lot information
            """)
        
        # Save to database
        with st.spinner("💾 Saving recommendation to MongoDB..."):
            rec = {
                "created_at": datetime.utcnow().isoformat(),
                "budget": budget,
                "hold_until": hold_date.isoformat(),
                "allocation": allocation,
                "explain": explain,
                "total_invested": total_invested,
                "leftover": remaining
            }
            rec = sanitize_for_mongo(rec)
            
            try:
                client = MongoClient(MONGO_URI)
                client[DB_NAME][COL_RECOMMEND].insert_one(rec)
                client.close()
                st.success(f"✅ Recommendation saved to MongoDB (collection: {COL_RECOMMEND})")
            except Exception as e:
                st.error(f"❌ Error saving to database: {str(e)}")
    
    else:
        # Welcome screen
        st.info("👈 Configure your parameters in the sidebar and click **Run Analysis** to start!")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 🎯 Features
            - AI-powered scoring
            - Multi-factor analysis
            - MILP optimization
            - Smart diversification
            """)
        
        with col2:
            st.markdown("""
            ### 📊 Scoring Factors
            - Base analysis score
            - Retail quota allocation
            - Fundamental metrics
            - Grey market premium
            """)
        
        with col3:
            st.markdown("""
            ### 🛡️ Risk Management
            - Diversification penalties
            - Lot-based allocation
            - Category awareness
            - Budget optimization
            """)

if __name__ == "__main__":
    main()