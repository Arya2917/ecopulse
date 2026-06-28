# EcoPulse — AI Audit Platform

EcoPulse audits machine-learning models across four dimensions: **Fairness**, **Explainability**, **Compliance**, and **Energy**. It also offers bias mitigation and PII masking.

Published Research:

* Survey: https://pijet.org/papers/volume-3%20issue-1/Final%20Revised%20Paper_Pijet-10_Dec25.pdf

The repo contains two independent folders:

```
/
├── backend/    # Python · Flask · REST API
└── frontend/   # React · Tailwind CSS
```

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |
| Ollama | Latest |

---

## 1 · Backend Setup

### 1.1 — Clone & navigate

```bash
git clone https://github.com/Arya2917/ecopulse
cd backend
```

### 1.2 — Create a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 1.3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

Some packages need an extra step after install:

```bash
# Download the spaCy English model (required by Presidio for PII detection)
python -m spacy download en_core_web_lg
```

### 1.4 — Run the backend server

```bash
python app.py
```

The API will start on **http://127.0.0.1:5000**.

> **Tip:** The server must be running before you launch the frontend.

### 1.5 — Install Ollama (Required for AI Copilot) - Optional

Download and install Ollama:

```bash
# Paste this in Powershell
irm https://ollama.com/install.ps1 | iex
```

Verify installation:

```bash
ollama --version
```

Pull the required model:

```bash
ollama pull llama3
```

If the Ollama server is not already running:

```bash
ollama serve
```

The AI Copilot automatically connects to Ollama
---

## 2 · Frontend Setup

### 2.1 — Navigate to the frontend folder

```bash
# From the repo root
cd frontend
```

### 2.2 — Install Node dependencies

```bash
npm install
```

### 2.3 — Start the development server

```bash
npm start
```

The app will open automatically at **http://localhost:3000**.

---

## 3 · Using the App

1. Open **http://localhost:3000** in your browser.
2. On the **Home** page, upload a CSV dataset and (optionally) a `.pkl` / `.onnx` model file.
3. Select the audit modules you want to run (Fairness, Explainability, Compliance, Energy).
4. Configure the target column, sensitive column, and thresholds, then click **Start Audit**.
5. The **Audit** page shows live progress. Acknowledge each module result to proceed to the next.
6. Download the full HTML report when the audit completes.
7. Use the **Mitigation** panel to apply bias-reduction techniques on your model or dataset.

---

## 4 · Project Structure

```
backend/
├── app.py                    # Flask entry point & route definitions
├── compliance_engine.py      # Compliance checks
├── requirements.txt
├── report/
│   └── generator.py          # HTML report builder
├── services/
│   ├── aggregator.py
│   ├── lime_service.py
│   ├── shap_service.py
│   └── model_detector.py
├── tasks/
│   ├── fairness.py
│   ├── explainability.py
│   ├── compliance.py
│   └── energy.py
└── utils/
    ├── fairness_metrics.py
    ├── mitigation.py
    ├── model_loader.py
    └── trust_score.py

frontend/
├── public/
│   └── index.html
└── src/
    ├── App.js
    ├── theme.js
    ├── components/
    │   └── Navbar.jsx
    ├── pages/
    │   ├── HomePage.jsx
    │   ├── AuditPage.jsx
    │   ├── MitigationPage.jsx
    │   └── GlossaryPage.jsx
    └── utils/
        └── api.js            # All backend API calls (base URL: http://127.0.0.1:5000)
```

---

## 5 · Common Issues

**`ModuleNotFoundError` on startup**
Make sure your virtual environment is activated and you ran `pip install -r requirements.txt`.

**spaCy model not found**
Run `python -m spacy download en_core_web_lg` inside the activated venv.

**Frontend shows network errors / blank results**
The backend must be running on port 5000 before starting the frontend. Check that nothing else is occupying that port (`lsof -i :5000` on Mac/Linux).

**`npm install` fails on Node version**
Upgrade Node.js to v18 or later: https://nodejs.org

---

## 6 · Environment Notes

- The frontend API base URL is hardcoded to `http://127.0.0.1:5000` in `src/utils/api.js`. Change this if you deploy the backend to a remote server.
- Runtime folders (`uploads/`, `reports/`, `saved_models_fairness/`) are created automatically by the backend and are excluded from version control via `.gitignore`.
