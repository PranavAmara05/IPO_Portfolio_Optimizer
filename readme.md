# 📈 IPO Portfolio Optimizer for Retail Investors

A comprehensive, data-driven system to analyze Indian IPOs, extract detailed financial information, score opportunities, and generate optimized portfolio allocation recommendations for retail investors.

---

## 🎯 Project Overview

This project automates the entire IPO analysis pipeline:

1. **Data Collection**: Scrapes latest IPO data from IPOWatch and InvestorGain
2. **Data Normalization**: Cleans and structures IPO information into MongoDB
3. **Detail Extraction**: Uses Perplexity AI to extract 15+ financial metrics per IPO
4. **Scoring**: Computes composite scores based on GMP, price, size, and fundamentals
5. **Portfolio Optimization**: Generates balanced, diversified allocation recommendations using MILP
6. **Interactive Dashboard**: Streamlit-based UI to explore recommendations with full explainability

---

## 📁 Project Structure

```
.
├── README.md                    # This file
├── BDA_copy_main.ipynb         # Main Jupyter notebook (primary workflow)
├── BDA_last_perplexity.ipynb   # Perplexity API experimentation notebook
├── recommender1.py             # Streamlit web application
├── requirements.txt            # Python dependencies (create with pip freeze)
└── .env                        # Environment variables (create locally)
```

---

## 📊 File Descriptions

### **BDA_copy_main.ipynb** (Main Notebook)

The core orchestrator that runs the full pipeline in 8 sequential cells:

#### **Cell 1: Fetch & Extract Latest IPOs**
- **Purpose**: Scrape latest IPO listings from IPOWatch and InvestorGain websites
- **Process**:
  - Fetches HTML from two sources (top sections only for recent IPOs)
  - Calls Perplexity AI to extract structured data
  - Parses markdown table output
  - Saves to `latest_ipo_comparison.md`
- **Output**: Markdown table with columns: IPO, Category, GMP_InvestorGain, GMP_IPOWatch, Issue_Price, Open_Date, Close_Date, GMP_Diff
- **Dependencies**: `requests`, Perplexity API key
- **Time**: ~30-60 seconds

#### **Cell 2: Normalize & Insert into MongoDB**
- **Purpose**: Parse the markdown table and persist to MongoDB with data cleaning
- **Process**:
  - Converts markdown table to pandas DataFrame
  - Extracts numeric values from text (e.g., "₹123" → 123)
  - Parses dates to ISO format (YYYY-MM-DD)
  - Cleans issue price ranges into {min, max, avg} structures
  - Inserts/updates records in `ipo_db.ipos` collection
- **Collections Updated**: `ipos` (one record per IPO with basic data)
- **Dependencies**: `pandas`, `pymongo`, `dateutil`
- **Time**: ~5 seconds

#### **Cell 3: Fetch Detailed IPO Pages & Extract 15 Fields**
- **Purpose**: For each IPO in MongoDB, scrape IPOWatch detail page and extract comprehensive financial info
- **Process**:
  - Generates multiple URL slug candidates (e.g., "hdfc-bank-ipo", "hdfc-ipo")
  - Fetches HTML from IPOWatch (up to 120KB per page)
  - Calls Perplexity with prompt to extract 15 fields:
    - Price Band, Issue Size, Issue Type, Listing Exchanges, IPO Dates
    - Market Lot & Amounts, Investor Quota Split, Anchor Details
    - Promoter Holdings (Pre/Post), Financial Performance (FY23–FY25)
    - Valuation Ratios (EPS, ROE, ROCE, D/E, NAV)
    - Lead Managers & Registrar, Company Overview, Peer Comparison, IPO (name)
  - Merges results into existing `extracted_fields` (incremental, non-destructive)
  - Stores extraction history for audit trail
- **Collections Updated**: `ipos` (field `extracted_fields` and `extraction_history`)
- **Uses PySpark**: Parallelizes across 4 workers for faster extraction
- **API Throttling**: 1.5s delay between calls to respect rate limits
- **Retry Logic**: 3 attempts per URL with exponential backoff
- **Time**: ~2–5 minutes (depends on number of IPOs and API availability)

#### **Cell 4: Score IPOs**
- **Purpose**: Compute investment scores (1–10) for each IPO based on multiple factors
- **Scoring Model**:
  ```
  Score = 0.45 × GMP_Score + 0.20 × Price_Score + 0.20 × Size_Score + 0.15 × Expectation_Score
  ```
  - **GMP Score**: % gain on listing (higher is better, capped at 100)
  - **Price Score**: Retail affordability (< ₹100 → 90pts, < ₹500 → 80pts, etc.)
  - **Size Score**: Issue size preference (mid-size ₹100cr–₹500cr preferred)
  - **Expectation Score**: Future listing gain estimate (GMP% / 2 + 50)
- **Output**: Final score 1–10 with verdict (Good ≥7, Moderate 4–7, Bad <4)
- **Collections Updated**: `ipo_analysis` (one record per scored IPO)
- **Uses PySpark**: Parallelizes scoring across 4 workers
- **Time**: ~10 seconds

#### **Cell 5: Interactive Portfolio Recommendation Engine**
- **Purpose**: Generate optimized allocation plan based on budget & hold-until date
- **Algorithm**:
  1. **Candidate Filtering**: Only include IPOs with composite score ≥ 5 that close before hold_until date
  2. **Composite Scoring** (enhanced from Cell 4):
     ```
     Composite = 0.30 × base_score + 0.25 × rq_score + 0.20 × fund_score 
               + 0.15 × (gmp_strength/10) + 0.10 × sentiment_score
     ```
     Where:
     - `base_score`: From Cell 4 (GMP/Price/Size/Expectation)
     - `rq_score`: Retail quota % normalized to 0–10
     - `fund_score`: Extracted from fundamentals (ROE, D/E, EPS heuristics)
     - `gmp_strength`: GMP % relative to issue price
     - `sentiment_score`: NLP on company overview (growth language vs. risk language)
  3. **Solver**:
     - Primary: MILP (Mixed Integer Linear Programming) via PuLP to maximize `Σ(composite × lots) - diversification_penalty`
     - Fallback: Improved greedy algorithm that:
       - Allocates 1 lot to top candidates (by composite/min_invest ratio)
       - Repeatedly fills top-3 candidates in round-robin
       - Fills remaining budget on best-ratio candidate
  4. **Output**: Allocation plan with per-IPO details, reasoning, and unexpended balance
- **Collections Updated**: `ipo_portfolio_recommendations`
- **Explainability**: Per-IPO breakdown of why to invest more / why to be cautious
- **Time**: ~5–10 seconds (MILP solving time varies)

#### **Cell 6: Sample Record Viewer**
- **Purpose**: Peek at one IPO record to verify structure
- **Output**: Pretty-printed JSON of first IPO in `ipos` collection
- **Time**: Instant

#### **Cells 7–8: Not shown in your notebooks**
- Typically would be for exporting results, visualization, or dashboard prep

---

### **BDA_last_perplexity.ipynb**

Experimentation notebook for Perplexity API integration. Contains:
- Initial API calls and response parsing logic
- Testing different prompt formats and table extraction patterns
- Debugging HTML fetch and markdown table parsing

**Use**: Reference for API debugging; not part of main pipeline.

---

### **recommender1.py** (Streamlit Web Dashboard)

A user-friendly web interface to interact with the optimization engine without running notebooks.

#### **Key Sections**:

1. **Imports & Configuration**
   - Streamlit UI framework
   - MongoDB connection
   - Math & data utilities for scoring

2. **Sidebar Controls**
   - Budget input (₹)
   - Hold-until date picker
   - Analysis mode selector (Basic / Detailed)

3. **Main Content Area**
   - **Eligible IPOs Table**: Shows all IPOs meeting criteria with scores & key metrics
   - **Allocation Plan**: Displays recommended lots per IPO, total invested, leftover
   - **Per-IPO Explainability**: Expandable sections with:
     - Composite score breakdown
     - Reasons to invest more
     - Reasons to be cautious
     - Component scores (base, retail quota, fundamentals, sentiment, GMP strength)
   - **Charts** (if Plotly available): Portfolio composition, score distribution

4. **Data Persistence**
   - Saves recommendation to MongoDB with timestamp
   - Stores for historical tracking

#### **How to Run Streamlit**:

```bash
# Install Streamlit
pip install streamlit

# Run the app
streamlit run recommender1.py

# Opens in browser at http://localhost:8501
```

---

## 🚀 Getting Started

### **Prerequisites**

- Python 3.9+ (tested on 3.11)
- MongoDB 4.4+ (local or Atlas)
- Perplexity API key (get free at https://www.perplexity.ai/api)

### **Installation Steps**

#### **1. Clone / Download Project**
```bash
cd /path/to/IPO_Portfolio_Optimizer
```

#### **2. Create Virtual Environment**
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

#### **3. Install Dependencies**
```bash
pip install requests
pip install pandas
pip install pymongo
pip install python-dateutil
pip install pyspark
pip install findspark
pip install streamlit
pip install pulp  # Optional: for MILP optimization
```

Or create `requirements.txt`:
```
requests>=2.31.0
pandas>=2.0.0
pymongo>=4.5.0
python-dateutil>=2.8.2
pyspark>=3.5.0
findspark>=1.4.2
streamlit>=1.28.0
pulp>=2.7.0
plotly>=5.17.0
```

Then:
```bash
pip install -r requirements.txt
```

#### **4. Set Environment Variables**

Create `.env` file in project root:
```env
MONGO_URI=mongodb://localhost:27017
# Or for MongoDB Atlas:
# MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/

PPLX_API_KEY=pplx-YOUR_KEY_HERE
```

Or set in shell:
```bash
# Windows (PowerShell):
$env:MONGO_URI = "mongodb://localhost:27017"
$env:PPLX_API_KEY = "pplx-YOUR_KEY_HERE"

# macOS/Linux:
export MONGO_URI="mongodb://localhost:27017"
export PPLX_API_KEY="pplx-YOUR_KEY_HERE"
```

#### **5. Ensure MongoDB is Running**
```bash
# If local MongoDB:
mongod

# Or use MongoDB Atlas connection string
```

---

## 🔄 Workflow: Step-by-Step

### **Full Pipeline Execution** (via Jupyter Notebook)

1. **Start Jupyter**:
   ```bash
   jupyter notebook
   ```
   Open `BDA_copy_main.ipynb`

2. **Run Cells in Order**:

   **Cell 1**: Fetch latest IPOs
   ```
   Input: None
   Output: latest_ipo_comparison.md (markdown table)
   ```

   **Cell 2**: Normalize & store in MongoDB
   ```
   Input: latest_ipo_comparison.md
   Output: IPO records in db.ipos collection
   ```

   **Cell 3**: Extract detailed fields (PySpark parallel)
   ```
   Input: IPO names from db.ipos
   Process: Fetch IPOWatch pages, call Perplexity API
   Output: extracted_fields merged into db.ipos documents
   Time: 2–5 min depending on # of IPOs
   ```

   **Cell 4**: Score IPOs (PySpark parallel)
   ```
   Input: db.ipos with extracted_fields
   Process: Compute scores 1–10
   Output: db.ipo_analysis collection with scores
   ```

   **Cell 5**: Portfolio recommendation
   ```
   Input: User budget & hold-until date (interactive)
   Process: MILP optimization or greedy allocation
   Output: db.ipo_portfolio_recommendations document
   ```

   **Cell 6**: View sample record
   ```
   Input: None
   Output: Pretty-printed JSON of first IPO
   ```

### **Quick Check** (Jupyter)

If you only want to test without re-extracting everything:
- Skip Cells 1–3 (use existing MongoDB data)
- Run Cell 4 (scoring)
- Run Cell 5 (recommendations)

---

## 🎮 Using the Streamlit Dashboard

### **Launch**:
```bash
streamlit run recommender1.py
```

### **User Flow**:

1. **Open Browser**: http://localhost:8501
2. **Sidebar**: Enter budget & hold-until date
3. **View**: Eligible IPOs table (auto-filters by date & score ≥ 5)
4. **Allocate**: Click "Generate Recommendation"
5. **Explore**: Expand each IPO to see detailed reasoning
6. **Export**: Recommendation auto-saved to MongoDB

### **Example Inputs**:
- Budget: `500000` (₹5 lakh)
- Hold Until: `2025-03-31`
- View: Top 5 recommendations by composite score

---

## 📋 Data Model

### **MongoDB Collections**

#### **ipos** (Basic IPO data)
```json
{
  "_id": ObjectId,
  "ipo": "HDFC Bank",
  "category": "Mainboard",
  "gmp_investorgain": 150,
  "gmp_ipowatch": 140,
  "gmp_diff": 10,
  "issue_price": { "min": 1495, "max": 1500, "avg": 1497.5 },
  "open_date": "2024-10-15",
  "close_date": "2024-10-18",
  "extracted_fields": {
    "Price Band": "₹1495–₹1500",
    "Issue Size": "₹500 cr",
    "Company Overview": "Leading IT company...",
    ...more fields...
  },
  "extraction_history": [
    {
      "extracted_at": "2024-10-20T10:30:00Z",
      "source_url": "...",
      "raw_markdown": "...",
      "fields_added": {...}
    }
  ],
  "inserted_at": "2024-10-15T08:00:00Z",
  "last_extracted_at": "2024-10-20T10:30:00Z"
}
```

#### **ipo_analysis** (Scoring results)
```json
{
  "_id": ObjectId,
  "ipo": "HDFC Bank",
  "gmp": 145,
  "issue_price": 1497.5,
  "issue_size": 5e9,
  "gmp_pct": 9.7,
  "score": 7.5,
  "verdict": "Good",
  "components": {
    "GMP": 82,
    "Price": 80,
    "Size": 85,
    "Expectation": 75
  },
  "scored_at": "2024-10-20T11:00:00Z",
  "status": "scored"
}
```

#### **ipo_portfolio_recommendations** (Allocation)
```json
{
  "_id": ObjectId,
  "created_at": "2024-10-20T11:30:00Z",
  "budget": 500000,
  "hold_until": "2025-03-31",
  "allocation": [
    {
      "ipo": "HDFC Bank",
      "lots": 3,
      "invested": 450000,
      "min_invest": 150000,
      "composite": 8.2
    },
    ...
  ],
  "explain": {
    "HDFC Bank": {
      "breakdown": {...},
      "reasons_more": [...],
      "reasons_less": [...]
    },
    ...
  },
  "total_invested": 450000,
  "leftover": 50000
}
```

---

## 🔧 Configuration & Tuning

### **In `BDA_copy_main.ipynb` Cell 4 (Scoring)**:

```python
# Weights for composite score
W_GMP = 0.45      # Grey Market Premium importance
W_PRICE = 0.20    # Price affordability
W_SIZE = 0.20     # Issue size preference
W_EXPECT = 0.15   # Expected listing gain
```

### **In `recommender1.py` (Allocation)**:

```python
MIN_INVEST_MAINBOARD = 15000       # Minimum for mainboard (retail)
DEFAULT_MAX_LOTS_PER_IPO = 3       # Avoid over-concentration
DIVERSIFICATION_WEIGHT = 0.10      # Penalty for concentration in MILP
TOP_FILL_K = 3                     # Round-robin fill top-K in greedy
```

Adjust these to match your investment philosophy.

---

## 📈 Scoring Formula Breakdown

### **Component 1: Base Score (Cell 4 Model)**
```
GMP_Score = min(max(GMP_pct, 0), 100)  # Grey market premium as %
Price_Score:
  < ₹100   → 90 pts (very affordable)
  < ₹500   → 80 pts
  < ₹1000  → 60 pts
  ≥ ₹1000  → 40 pts (less affordable)
Size_Score:
  < ₹100cr     → 40 pts (too small)
  ₹100–500cr   → 70 pts (good)
  ₹500cr–5000cr → 90 pts (ideal)
  ≥ ₹5000cr    → 60 pts (too large for retail)
```

**Result**: `base_score = 0.45×GMP + 0.20×Price + 0.20×Size + 0.15×Expectation`

### **Component 2: Composite Score (recommender1.py)**
```
composite = 0.30 × base_score 
          + 0.25 × rq_score          (retail quota normalized)
          + 0.20 × fund_score        (ROE, D/E, EPS heuristics)
          + 0.15 × (gmp_strength/10) (GMP % relative to price)
          + 0.10 × sentiment_score   (NLP on company overview)
```

**Range**: 0–10

**Verdict**:
- ≥ 7.0 → **Good** (recommended)
- 4.0–6.9 → **Moderate** (possible, but verify fundamentals)
- < 4.0 → **Skip** (or only small allocation)

---

## ⚙️ Algorithm Details

### **MILP Optimization** (Primary in recommender1.py)

**Objective**:
```
Maximize: Σ(composite_i × lots_i) - DIVERSIFICATION_WEIGHT × Σ(lots_i²)
Subject to:
  Σ(min_invest_i × lots_i) ≤ budget
  0 ≤ lots_i ≤ DEFAULT_MAX_LOTS_PER_IPO  ∀ i
  lots_i ∈ ℤ (integer)
```

**Solver**: CBC (Coin-or branch and cut) via PuLP library

**Time**: Usually < 10 seconds

### **Greedy Fallback** (If MILP unavailable or time-limited)

1. Sort IPOs by `composite / min_invest` (score per rupee) descending
2. Allocate 1 lot to each top candidate if budget allows
3. Repeatedly allocate 1 lot to top-3 candidates in round-robin
4. Fill remaining budget on best-ratio candidate
5. Minimizes leftover cash

---

## 🐛 Troubleshooting

### **Issue: "MongoDB connection refused"**
- **Solution**: Ensure MongoDB is running (`mongod`) or check MONGO_URI in .env
- **Test**: `mongo mongodb://localhost:27017` (MongoDB CLI)

### **Issue: "Perplexity API rate limit exceeded"**
- **Solution**: Increase `API_DELAY` in Cell 3 (currently 1.5s)
- **Alternative**: Use batch processing with smaller chunks

### **Issue: "No table extracted for IPO"**
- **Solution**: Check Perplexity API response in Cell 3's error output
- **Debug**: Print `result_text[:400]` to see raw LLM response

### **Issue: Streamlit crashes on budget input**
- **Solution**: Ensure MongoDB is accessible; restart with `streamlit run --logger.level=debug recommender1.py`

### **Issue: "PuLP not installed"**
- **Solution**: `pip install pulp` (falls back to greedy if missing)

---

## 📚 Example Workflow

### **Scenario: Retail investor with ₹5 lakh budget**

1. **Run Cell 1–2** (5 min):
   - Fetches latest IPOs (e.g., HDFC, TCS, Infosys)
   - Stores in MongoDB

2. **Run Cell 3** (3 min):
   - Extracts detailed fields for each IPO

3. **Run Cell 4** (instant):
   - Computes base scores

4. **Run Cell 5** (choose mode):
   - **Option A**: Jupyter interactive → enter budget & date
   - **Option B**: Streamlit dashboard → same inputs via web UI

5. **View Results**:
   ```
   Allocation Plan:
   - HDFC Bank: 3 lots, ₹4,50,000 (composite 8.2)
   - TCS: 2 lots, ₹2,00,000 (composite 7.5)
   - Leftover: ₹50,000
   ```

6. **Explainability** (Streamlit):
   - Click "HDFC Bank" → see breakdown of composite score
   - See "Reasons to invest more": High GMP strength 9.7%, Retail quota 35%
   - See "Reasons to be cautious": None identified

---

## 📊 Expected Output Examples

### **Latest IPOs Table** (after Cell 1–2):
```
| IPO | Category | GMP_InvestorGain | GMP_IPOWatch | Issue_Price | Open_Date | Close_Date |
| --- | --- | --- | --- | --- | --- | --- |
| HDFC Bank | Mainboard | 150 | 145 | ₹1495–1500 | 2024-10-15 | 2024-10-18 |
| TCS | Mainboard | 120 | 115 | ₹2500–2600 | 2024-10-20 | 2024-10-23 |
```

### **Scores** (after Cell 4):
```
HDFC Bank: 7.5/10 (Good) — GMP 9.7%, Size ₹5000cr
TCS: 7.2/10 (Good) — GMP 8.8%, Size ₹3000cr
ABC SME: 5.5/10 (Moderate) — GMP 15%, Size ₹50cr
```

### **Recommendation** (after Cell 5 / Streamlit):
```
Budget: ₹5,00,000
Allocation:
  HDFC Bank: ₹4,50,000 (3 lots @ ₹1,50,000/lot)
  TCS: ₹2,00,000 (2 lots @ ₹1,00,000/lot)
  
Unexpended: ₹50,000
```

---

## 🎓 Learning Resources

- **IPO Basics**: https://www.investopedia.com/terms/i/ipo.asp
- **Grey Market Premium**: https://www.investopedia.com/terms/g/greymarketpremium.asp
- **PuLP MILP**: https://coin-or.github.io/Pulp/
- **MongoDB**: https://docs.mongodb.com/
- **Streamlit**: https://docs.streamlit.io/

---

## 📝 License

This project is provided as-is for educational and personal use.

---

## ✉️ Support & Contribution

For issues, improvements, or questions:
1. Check the **Troubleshooting** section above
2. Review logs in Jupyter output or Streamlit console
3. Verify MongoDB and API keys are correctly configured

---

## 📦 Dependencies Summary

| Library | Purpose | Version |
| --- | --- | --- |
| `requests` | HTTP fetching (IPOWatch pages) | ≥2.31.0 |
| `pandas` | Data manipulation & tables | ≥2.0.0 |
| `pymongo` | MongoDB client | ≥4.5.0 |
| `python-dateutil` | Date parsing & handling | ≥2.8.2 |
| `pyspark` | Parallel data processing | ≥3.5.0 |
| `findspark` | PySpark initialization | ≥1.4.2 |
| `streamlit` | Web dashboard framework | ≥1.28.0 |
| `pulp` | MILP optimization solver | ≥2.7.0 |
| `plotly` | Interactive visualizations | ≥5.17.0 (optional) |

---

## 🗓️ Version History

- **v1.0** (2024-10): Initial release
  - Core pipeline: fetch → normalize → extract → score → allocate
  - Jupyter notebook + Streamlit dashboard
  - MILP optimization with greedy fallback

---

**Happy investing! 🚀📊**