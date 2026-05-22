# FakeNews Detector - Complete System Analysis

## 1. CURRENT DATABASE SETUP

### Storage Method

**Type**: JSON File-Based (NOT MongoDB despite pymongo in requirements.txt)

**File Location**: [history.json](history.json) (created at runtime in FakeNews/ directory)

### Collections Structure

**Single collection equivalent**: `history` array

### Data Schema

Each history entry stores the following structure:

```json
{
  "timestamp": "2024-05-13 14:30:45 UTC",
  "source_type": "url|text",
  "query": "article_text_or_url_provided",
  "status": "Real|Fake|Unreliable",
  "confidence_score": 94.2,
  "domain": "example.com",
  "risk_score": 0,
  "matched_tokens": ["token1", "token2"],
  "clickbait_matches": ["shocking", "viral"],
  "summary": "first_500_chars_of_article",
  "model_results": [
    {
      "name": "Logistic Regression",
      "label": "Real|Fake",
      "true_probability": 94.2,
      "fake_probability": 5.8
    }
  ]
}
```

### Data Storage Location

- **Active session**: In-memory `history` list variable
- **Persistent**: JSON file in [FakeNews/history.json](FakeNews/)
- **Data loading**: Happens on app startup via `load_history()` function
- **Data saving**: After every prediction via `save_history()` function

**Note**: MongoDB is in requirements.txt but **NOT IMPLEMENTED** - the app uses file-based storage instead.

---

## 2. FLASK APP ROUTES

All routes defined in [FakeNews/app.py](FakeNews/app.py):

### Public Routes (No Authentication Required)

| Route         | Method | Purpose                      | Response                                                                                                                  |
| ------------- | ------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `/`           | GET    | Home landing page            | Renders [index.html](templates/index.html)                                                                                |
| `/home`       | GET    | News verification input page | Renders [home.html](templates/home.html) with form for article/URL input                                                  |
| `/predict`    | POST   | Process news verification    | Process article text or URL, run ML models, save to history, render [result.html](templates/result.html) with predictions |
| `/dashboard`  | GET    | Analytics dashboard          | Shows statistics: total checks, fake/real/unreliable counts, average confidence                                           | Renders [dashboard.html](templates/dashboard.html)         |
| `/history`    | GET    | View all checks history      | Display all entries from history array (5 most recent on dashboard)                                                       | Renders [history.html](templates/history.html)             |
| `/admin`      | GET    | Admin monitoring panel       | Display latest check and top 5 from history                                                                               | Renders [admin.html](templates/admin.html)                 |
| `/news`       | GET    | Authentic news feed          | Fetch articles from NewsData.io API (apikey: pub_25325f37af89bd7d4d9cbed5370e44260af86)                                   | Renders [authenticNews.html](templates/authenticNews.html) |
| `/report`     | GET    | Report form page             | Show form to submit fake news report                                                                                      | Renders [report.html](templates/report.html)               |
| `/submit`     | POST   | Submit fake news report      | Extract form data, send email to sachinu760@gmail.com, redirect                                                           | Renders [mailResponse.html](templates/mailResponse.html)   |
| `/recentFake` | GET    | Recent fake news page        | Display recent fake news                                                                                                  | Renders [recentFake.html](templates/recentFake.html)       |
| `/about`      | GET    | About page                   | Project information                                                                                                       | Renders [about.html](templates/about.html)                 |

### Route Code References

- Main routes: [app.py#L163-L212](FakeNews/app.py#L163-L212)
- Predict route: [app.py#L158-L185](FakeNews/app.py#L158-L185)
- Dashboard route: [app.py#L186-L198](FakeNews/app.py#L186-L198)
- Email config: [app.py#L256-L265](FakeNews/app.py#L256-L265)

---

## 3. ML MODEL DETAILS

### Trained Models (Ensemble Approach)

**4-Model Voting Ensemble** - Uses majority voting for final prediction

#### Individual Models

1. **Logistic Regression** (LR)
   - File: [LrModel.pkl](FakeNews/LrModel.pkl)
   - Accuracy: ~94%
   - Type: Linear classifier
   - Reference: [Fake_new_detection.ipynb](Fake_new_detection.ipynb) cell for LogisticRegression

2. **Decision Tree** (DT)
   - File: [DtModel.pkl](FakeNews/DtModel.pkl)
   - Accuracy: ~89%
   - Type: Tree-based classifier
   - Reference: [Fake_new_detection.ipynb](Fake_new_detection.ipynb) cell for DecisionTreeClassifier

3. **Gradient Boosting** (GB)
   - File: [GBModel.pkl](FakeNews/GBModel.pkl)
   - Type: Ensemble boosting algorithm
   - Reference: [app.py#L112-L135](FakeNews/app.py#L112-L135) where loaded as GBModel

4. **Random Forest** (RF)
   - File: [RFModel.pkl](FakeNews/RFModel.pkl)
   - Type: Ensemble random trees
   - Reference: [app.py#L112-L135](FakeNews/app.py#L112-L135) where loaded as RFModel

### Feature Extraction

**Vectorizer**: TF-IDF (Term Frequency-Inverse Document Frequency)

- File: [vectorizer.pkl](FakeNews/vectorizer.pkl)
- Type: `sklearn.feature_extraction.text.TfidfVectorizer`
- Training: Fitted on training dataset in notebook
- Reference: [Fake_new_detection.ipynb](Fake_new_detection.ipynb) - TfidfVectorizer section

### Training Data

- **Fake News Dataset**: CSV file (external, 43,642 samples with class=0)
- **True News Dataset**: CSV file (external, 34,975 samples with class=1)
- **Combined Training Set**: 78,617 total samples
- **Train/Test Split**: 75% training, 25% testing (~19,655 test samples)

### Training Preprocessing

```python
def textCleaner(text):
    # Lowercase conversion
    # Remove brackets content
    # Remove URLs
    # Remove HTML tags
    # Remove punctuation
    # Remove digits/numbers
    # Normalize whitespace
```

Reference: [app.py#L68-L77](FakeNews/app.py#L68-L77) and [Fake_new_detection.ipynb](Fake_new_detection.ipynb)

### Prediction Pipeline

1. Clean text input via `textCleaner()`
2. Transform via TF-IDF vectorizer
3. Get predictions from all 4 models
4. Calculate probabilities: `predict_proba()` if available, else derive from binary prediction
5. Vote: Count true_votes vs fake_votes
6. Final decision:
   - true_votes > fake_votes → **Real**
   - true_votes == fake_votes → **Unreliable**
   - fake_votes > true_votes → **Fake**
7. Confidence score = average of true_probability across all models × 100

Reference: [app.py#L112-L135](FakeNews/app.py#L112-L135) `build_model_results()` function

---

## 4. AUTHENTICATION SYSTEM

### Current Authentication Status

**❌ NO AUTHENTICATION IMPLEMENTED**

### Key Findings:

- **All routes are publicly accessible** - No login/auth checks on any route
- **No user sessions** - Flask-Session not in dependencies
- **No protected endpoints** - Admin page (`/admin`) has no access control despite name
- **No authentication middleware** - No decorators or checks in app.py
- **No username/password system** - No user database or credentials validation

### Security Implications:

- Anyone can access dashboard, admin panel, history
- No way to limit data access per user
- No audit trail of who accessed what
- Email reports can be submitted by anyone

### Templates Analysis:

- [admin.html](templates/admin.html) - Shows navigation links but **no login required**
- [dashboard.html](templates/dashboard.html) - Public analytics display
- [home.html](templates/home.html) - Public prediction form
- [index.html](templates/index.html) - Landing page with navigation links

### Frontend Navigation

All template pages provide direct links to all other pages without any authentication barriers:

```html
<a href="/dashboard">Dashboard</a>
<a href="/history">History</a>
<a href="/admin">Admin</a>
<a href="/home">Check News</a>
```

---

## 5. DATA STORAGE & PERSISTENCE

### What Information is Stored

**Stored on Every Prediction** ([app.py#L196-L210](FakeNews/app.py#L196-L210)):

1. **Timestamp** - Exact UTC time of prediction
2. **Source Type** - "url" or "text"
3. **Raw Query** - Original input (article text or URL)
4. **Prediction Result** - Status (Real/Fake/Unreliable)
5. **Confidence Score** - 0-100% based on model agreement
6. **Domain Analysis** (if URL input):
   - Domain name extracted
   - Risk score (count of suspicious tokens found)
   - Matched suspicious tokens list
7. **Clickbait Detection**:
   - List of matched clickbait keywords found
8. **Content Summary** - First 500 characters of article
9. **Model Results** - Individual predictions from each of 4 models:
   - Model name
   - Predicted label (Real/Fake)
   - True probability percentage
   - Fake probability percentage

### Storage Timing

| Event                  | Timing                       | File                                                                                         |
| ---------------------- | ---------------------------- | -------------------------------------------------------------------------------------------- |
| Prediction submitted   | Immediately after processing | [history.json](FakeNews/history.json)                                                        |
| App startup            | On app initialization        | Loaded from disk                                                                             |
| User reports fake news | After email sent             | [history.json](FakeNews/history.json) NOT included (just email sent to sachinu760@gmail.com) |

### Storage Method

- **Format**: JSON array of objects
- **Location**: [FakeNews/history.json](FakeNews/history.json)
- **Persistence**: Survives app restarts (file-based)
- **Max items**: Unlimited (no cleanup policy)
- **Previous entries location**: New predictions inserted at beginning (index 0)

### File Operations Code

**Load at startup** ([app.py#L45-L52](FakeNews/app.py#L45-L52)):

```python
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as history_file:
                return json.load(history_file)
        except Exception:
            return []
    return []
```

**Save after each prediction** ([app.py#L55-L57](FakeNews/app.py#L55-L57)):

```python
def save_history(history_data):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as history_file:
        json.dump(history_data, history_file, indent=2)
```

### What is NOT Stored

- ❌ User identities or sessions
- ❌ Email addresses (only reports sent to admin email)
- ❌ IP addresses or source information
- ❌ Error logs or exceptions
- ❌ Model retraining data or metrics

### Data Retrieval

1. **Dashboard** ([app.py#L186-L198](FakeNews/app.py#L186-L198)):
   - Shows last 5 entries: `history[:5]`
   - Calculates statistics from entire history

2. **History Page** ([app.py#L182-L183](FakeNews/app.py#L182-L183)):
   - Shows entire history: `history`

3. **Admin Page** ([app.py#L201-L203](FakeNews/app.py#L201-L203)):
   - Latest entry: `history[0]`
   - Top 5: `history[:5]`

---

## 6. DEPENDENCIES & EXTERNAL SERVICES

### Python Dependencies (requirements.txt)

```
Flask==3.0.3                          # Web framework
flask-mail==0.10.0                    # Email sending (SMTP)
scikit-learn==1.5.1                   # ML models
pandas==2.2.2                         # Data processing
requests==2.32.3                      # HTTP requests
pymongo==4.8.0                        # (NOT USED - no MongoDB connection)
opencv-python==4.10.0.84              # (Listed but not used in app.py)
numpy==1.26.4                         # Numerical computing
joblib==1.4.2                         # Model serialization
```

### External APIs

- **NewsData.io API**: [https://newsdata.io/api/1/news](https://newsdata.io/api/1/news)
  - Used in `/news` route
  - API Key: `pub_25325f37af89bd7d4d9cbed5370e44260af86`
  - Returns authentic news articles

### Email Configuration ([app.py#L256-L265](FakeNews/app.py#L256-L265))

```python
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'sachinu760@gmail.com'
app.config['MAIL_PASSWORD'] = 'dqlbhfpzefdhncgx'  # App-specific password
app.config['MAIL_USE_SSL'] = True
```

---

## 7. CONTENT ANALYSIS FEATURES

### Clickbait Detection

25 keywords monitored ([app.py#L24-L35](FakeNews/app.py#L24-L35)):

- "shocking", "you won't believe", "breaking", "viral", "secret", "exposed"
- "unbelievable", "miracle", "sensational", "must read", "confirmed"
- "outrage", "exclusive", "money", "fake", "hoax", "urgent"
- "alert", "scandal", "bombshell", "scary", "hidden"
- "last chance", "don't miss", "act now", "reveal", "shocker"

### Domain Risk Assessment

13 suspicious domain tokens ([app.py#L36-L43](FakeNews/app.py#L36-L43)):

- "click", "buzz", "update", "alert", "breaking", "truth", "info"
- "report", "today", "instant", "viral", "latest", "exclusive"
- "news24", "newsnow", "worldnews", "daily", "headline", "shocking"

### URL Content Extraction

- Fetches article title from `<title>` tag
- Strips JavaScript and CSS
- Removes HTML tags
- Returns first ~2000 characters via `extract_title_and_text_from_url()` ([app.py#L81-L96](FakeNews/app.py#L81-L96))

---

## 8. FILE STRUCTURE REFERENCE

```
FakeNewsDetector/
├── FakeNews/
│   ├── app.py                  # Flask application (main logic)
│   ├── LrModel.pkl             # Logistic Regression model
│   ├── DtModel.pkl             # Decision Tree model
│   ├── RFModel.pkl             # Random Forest model
│   ├── GBModel.pkl             # Gradient Boosting model
│   ├── vectorizer.pkl          # TF-IDF vectorizer
│   ├── history.json            # Persistent history storage
│   └── __pycache__/            # Python cache
├── templates/                  # HTML templates (14 files)
│   ├── index.html              # Home page
│   ├── home.html               # Prediction form
│   ├── result.html             # Prediction results
│   ├── dashboard.html          # Analytics dashboard
│   ├── history.html            # History view
│   ├── admin.html              # Admin panel
│   ├── authenticNews.html      # Authenticated news feed
│   ├── report.html             # Report form
│   ├── mailResponse.html       # Report confirmation
│   ├── about.html              # About page
│   ├── fake.html, true.html, unreliable.html  # Status pages
│   └── recentFake.html         # Recent fake news
├── static/                     # CSS & images
│   ├── home.css, fake.css, true.css, unreliable.css
│   ├── news.css, styles.css
│   └── images/
├── Fake_new_detection.ipynb    # Model training notebook
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation
└── LICENSE                     # MIT License
```

---

## 9. SECURITY & RECOMMENDATIONS

### Current Vulnerabilities

1. **No authentication** - All data publicly accessible
2. **API key exposed** - NewsData.io API key in source code
3. **Email credentials exposed** - Gmail credentials visible in code
4. **No rate limiting** - Unlimited predictions possible
5. **No SQL injection risk** (good - uses JSON instead of DB)
6. **No CSRF protection** mentioned

### Recommended Improvements

1. Implement user authentication (Flask-Login)
2. Move credentials to environment variables
3. Add MongoDB integration for scalability
4. Implement API rate limiting
5. Add data validation and error handling
6. Encrypt sensitive stored data
7. Add logging and audit trails
8. Implement data retention policies

---

**Analysis Generated**: May 13, 2026
**System Status**: Fully Operational (Development/Demo Phase)
