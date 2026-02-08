# Security Review Report - LLM Council

**Review Date:** 2026-02-08  
**Reviewed By:** Senior Application Security Engineer  
**Repository:** KriRuo/llm-council  
**Commit:** Latest (security review)

---

## Executive Summary

LLM Council is a FastAPI-based web application that queries multiple LLMs via OpenRouter and presents their responses in a 3-stage council deliberation format. The application consists of a Python backend (FastAPI) and React frontend with JSON-based local storage.

**Overall Security Posture:**  
The application has **MODERATE to HIGH security risk** in its current state. It is designed for local/single-user deployment, but contains several vulnerabilities that could be exploited if exposed to untrusted networks or users. The main concerns are:

1. **Path Traversal vulnerability** allowing arbitrary file system access
2. **No authentication or authorization** mechanisms - anyone with network access can use the API
3. **API key exposure risk** - no validation that the key exists or proper error handling
4. **No rate limiting** - susceptible to DoS and API cost exhaustion attacks
5. **Missing input validation** - user input is passed directly to external APIs without sanitization

The application appears to be a personal project designed for trusted local use, but several security hardening measures are recommended before any broader deployment.

**Top 3 Risks to Address First:**

1. **Critical: Path Traversal in Conversation Storage** - Malicious conversation IDs can read/write arbitrary files on the system
2. **High: No Authentication/Rate Limiting** - Anyone can exhaust OpenRouter API credits and access all stored conversations
3. **High: API Key Not Validated** - Application starts without checking if OPENROUTER_API_KEY is set, leading to confusing errors

---

## Findings

### 1. Path Traversal Vulnerability in Conversation Storage

**Severity:** CRITICAL  
**Affected files:** `backend/storage.py` (lines 16-18, 48-64, 91-102)

**Description:**  
The `get_conversation_path()` function constructs file paths using user-controlled `conversation_id` without validation. An attacker can use path traversal sequences (`../`) in the conversation ID to read or write arbitrary JSON files on the filesystem.

```python
def get_conversation_path(conversation_id: str) -> str:
    return os.path.join(DATA_DIR, f"{conversation_id}.json")
```

**Impact:**  
- **Data Exfiltration:** Read any JSON file on the system the process has access to
- **Arbitrary File Write:** Create/overwrite files in accessible directories
- **Information Disclosure:** Enumerate filesystem structure
- **Example:** `GET /api/conversations/../../../etc/passwd%00` (null byte may not work with modern Python, but `../../sensitive-config` would)

**Likelihood:** HIGH (trivial to exploit if attacker has API access)

**Recommendation:**
1. Validate that `conversation_id` is a valid UUID format before use
2. Use `os.path.basename()` or `pathlib.Path().name` to strip path components
3. Verify the resolved path stays within `DATA_DIR` using `os.path.commonpath()`

**Example Fix:**
```python
import uuid
from pathlib import Path

def get_conversation_path(conversation_id: str) -> str:
    # Validate UUID format
    try:
        uuid.UUID(conversation_id)
    except ValueError:
        raise ValueError(f"Invalid conversation ID format: {conversation_id}")
    
    # Construct path safely
    safe_filename = f"{conversation_id}.json"
    full_path = Path(DATA_DIR) / safe_filename
    
    # Ensure path is within DATA_DIR
    try:
        full_path.resolve().relative_to(Path(DATA_DIR).resolve())
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {conversation_id}")
    
    return str(full_path)
```

---

### 2. No Authentication or Authorization

**Severity:** HIGH  
**Affected files:** `backend/main.py` (all endpoints)

**Description:**  
The API has no authentication mechanism. Anyone who can reach the backend (port 8001) can:
- List all conversations
- Read any conversation content
- Create unlimited conversations
- Send messages (consuming OpenRouter API credits)
- Access the streaming endpoint

The CORS configuration allows `localhost:5173` and `localhost:3000`, suggesting local-only deployment, but the server binds to `0.0.0.0` which accepts connections from any network interface.

**Impact:**  
- **Unauthorized Access:** Any network user can access all stored conversations
- **API Cost Exhaustion:** Attackers can drain OpenRouter credits
- **Data Breach:** Conversations may contain sensitive information
- **Resource Exhaustion:** Unbounded conversation/message creation

**Likelihood:** HIGH (if exposed to network), LOW (if strictly localhost)

**Recommendation:**
1. **If single-user/local only:**
   - Bind to `127.0.0.1` instead of `0.0.0.0` in `main.py` line 199
   - Add clear documentation that this is for local use only
   - Consider adding a simple API key header check

2. **If multi-user deployment:**
   - Implement OAuth2 or JWT-based authentication
   - Add per-user conversation isolation
   - Store API keys per-user (not shared)

3. **Immediate mitigation:**
```python
# In main.py
if __name__ == "__main__":
    import uvicorn
    # Bind to localhost only for security
    uvicorn.run(app, host="127.0.0.1", port=8001)
```

---

### 3. Missing API Key Validation

**Severity:** HIGH  
**Affected files:** `backend/config.py` (line 9)

**Description:**  
The application loads `OPENROUTER_API_KEY` from environment but never validates it exists or has a valid format. The application starts successfully even with no API key, then fails later with cryptic HTTP errors when trying to make requests.

```python
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Could be None
```

**Impact:**  
- **Startup Confusion:** App appears to work but fails on first query
- **Information Disclosure:** Error messages may leak internal details
- **Poor UX:** Users don't know configuration is wrong until they try to use it

**Likelihood:** MEDIUM (likely for new users)

**Recommendation:**
Add startup validation in `config.py`:

```python
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY environment variable is required. "
        "Create a .env file with: OPENROUTER_API_KEY=sk-or-v1-..."
    )

if not OPENROUTER_API_KEY.startswith("sk-or-"):
    import sys
    print(f"WARNING: OPENROUTER_API_KEY doesn't match expected format (sk-or-*)", file=sys.stderr)
```

---

### 4. No Rate Limiting

**Severity:** HIGH  
**Affected files:** `backend/main.py` (all POST endpoints)

**Description:**  
There is no rate limiting on API endpoints. An attacker (or misconfigured client) can:
- Spam message requests, exhausting OpenRouter API credits
- Create unlimited conversations, filling disk space
- DoS the application through resource exhaustion

The lack of rate limiting is especially concerning because:
- Each message triggers multiple external API calls (Stage 1: 4 models, Stage 2: 4 models, Stage 3: 1 model = 9 API calls)
- OpenRouter charges per token, so cost grows linearly with spam
- Long-running requests (streaming) are not bounded

**Impact:**  
- **Financial Loss:** Unlimited API credit consumption
- **Service Disruption:** Resource exhaustion via spam
- **Disk Exhaustion:** Unlimited conversation storage

**Likelihood:** HIGH (if exposed), MEDIUM (even localhost - buggy client)

**Recommendation:**
Implement rate limiting using `slowapi` or similar:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/conversations/{conversation_id}/message")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def send_message(request: Request, conversation_id: str, ...):
    ...
```

Add to `pyproject.toml`:
```toml
dependencies = [
    ...
    "slowapi>=0.1.9",
]
```

---

### 5. Missing Input Validation and Sanitization

**Severity:** MEDIUM  
**Affected files:** `backend/main.py` (line 34, 83-123), `backend/council.py` (entire file)

**Description:**  
User input (`request.content`) is passed directly to:
1. External LLM APIs without sanitization
2. String formatting in prompt construction (potential injection)
3. File storage without content validation

While Pydantic validates the `content` field exists and is a string, there are no checks for:
- Maximum length (could cause out-of-memory or excessive API costs)
- Injection attacks in prompt construction (though LLM APIs handle this)
- Malicious content that might confuse downstream processing

**Example concern in `council.py` line 64:**
```python
ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}
...
```

If `user_query` contains special characters or escape sequences, it could potentially cause issues.

**Impact:**  
- **API Cost Exhaustion:** No max length allows extremely long inputs
- **Resource Exhaustion:** Large messages consume memory and storage
- **Potential Injection:** Malformed input could confuse LLM prompt parsing

**Likelihood:** MEDIUM

**Recommendation:**
Add input validation:

```python
class SendMessageRequest(BaseModel):
    content: str
    
    @validator('content')
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        if len(v) > 50000:  # ~50KB limit
            raise ValueError("Message content exceeds maximum length (50,000 characters)")
        return v.strip()
```

Add request size limits to FastAPI:
```python
app = FastAPI(
    title="LLM Council API",
    max_request_size=1024 * 1024  # 1MB max request size
)
```

---

### 6. Information Disclosure via Error Messages

**Severity:** MEDIUM  
**Affected files:** `backend/openrouter.py` (line 52), `backend/main.py` (multiple locations)

**Description:**  
Error handling prints full exception details and returns generic errors, which could leak:
- Internal system paths
- API endpoint details
- Stack traces in logs
- Model identifiers and configuration

Example:
```python
except Exception as e:
    print(f"Error querying model {model}: {e}")  # Logs to console, visible if attacker has log access
    return None
```

**Impact:**  
- **Information Disclosure:** Attackers learn about internal structure
- **Attack Surface Mapping:** Error messages reveal implementation details

**Likelihood:** LOW (requires log access or verbose error responses)

**Recommendation:**
1. Use proper logging with levels (don't print to stdout)
2. Return sanitized errors to clients
3. Log detailed errors securely for debugging

```python
import logging

logger = logging.getLogger(__name__)

except Exception as e:
    logger.error(f"Error querying model {model}", exc_info=True)
    # Don't return detailed error to client
    return None
```

---

### 7. Insecure Server Binding (0.0.0.0)

**Severity:** MEDIUM  
**Affected files:** `backend/main.py` (line 199), `start.sh` (line 10)

**Description:**  
The backend binds to `0.0.0.0`, accepting connections from any network interface. Combined with no authentication, this exposes the API to:
- Local network users (if on shared WiFi)
- VPN users
- Potentially internet if port-forwarded

**Impact:**  
- Expands attack surface from localhost-only to network-accessible
- Enables remote exploitation of all other vulnerabilities

**Likelihood:** MEDIUM (depends on network environment)

**Recommendation:**
Bind to `127.0.0.1` for local-only access:

```python
# main.py line 199
uvicorn.run(app, host="127.0.0.1", port=8001)
```

Document in README that network access requires explicit reverse proxy setup with authentication.

---

### 8. CORS Configuration May Be Too Permissive

**Severity:** LOW  
**Affected files:** `backend/main.py` (lines 18-24)

**Description:**  
CORS is configured to allow:
- `http://localhost:5173` (Vite dev server)
- `http://localhost:3000` (alternative)
- All methods and headers
- Credentials

For local development this is reasonable, but:
- No HTTPS enforcement (though localhost doesn't need it)
- `allow_credentials=True` with specific origins is correct
- Wildcard methods/headers could be more restrictive

**Impact:**  
- Minimal in current configuration (specific origins)
- Could be issue if origins are made more permissive

**Likelihood:** LOW

**Recommendation:**
Current configuration is acceptable for local development. If deploying to production:

```python
# Production example
origins = [
    "https://your-domain.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Only what's needed
    allow_headers=["Content-Type", "Authorization"],  # Specific headers
)
```

---

### 9. No HTTPS / TLS

**Severity:** LOW (for localhost), HIGH (if networked)  
**Affected files:** Configuration, deployment

**Description:**  
Application uses HTTP only. For localhost this is acceptable, but if accessed over network:
- API key in Authorization header (OpenRouter) visible in plaintext
- Conversation data transmitted unencrypted
- Session hijacking possible

**Impact:**  
- **Data Interception:** API keys and conversation content visible to network sniffers
- Only relevant if application is network-accessible

**Likelihood:** LOW (designed for localhost)

**Recommendation:**
1. Document that HTTPS is required for any network deployment
2. Provide example reverse proxy configs (nginx, Caddy) with automatic HTTPS
3. Consider using mkcert for local HTTPS development

---

### 10. Directory Traversal in list_conversations()

**Severity:** LOW  
**Affected files:** `backend/storage.py` (lines 81-107)

**Description:**  
The `list_conversations()` function lists all `.json` files in `DATA_DIR` without validating they are actual conversation files. If an attacker can write arbitrary `.json` files to the directory (via the path traversal vulnerability), they could:
- Cause errors by creating malformed JSON
- Potentially inject data into the conversation list

**Impact:**  
- **DoS:** Malformed JSON files cause crashes
- **Information Leakage:** Attacker-created files appear in UI
- Requires combining with path traversal vulnerability

**Likelihood:** LOW (requires existing path traversal exploit)

**Recommendation:**
Validate JSON structure when listing:

```python
def list_conversations() -> List[Dict[str, Any]]:
    ensure_data_dir()
    conversations = []
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    # Validate required fields
                    if 'id' in data and 'created_at' in data and 'messages' in data:
                        conversations.append({
                            "id": data["id"],
                            "created_at": data["created_at"],
                            "title": data.get("title", "New Conversation"),
                            "message_count": len(data["messages"])
                        })
            except (json.JSONDecodeError, IOError, KeyError) as e:
                # Log but skip invalid files
                logger.warning(f"Skipping invalid conversation file {filename}: {e}")
                continue
    
    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations
```

---

## Dependency & Supply Chain Risks

### Python Dependencies (pyproject.toml, uv.lock)

**Current Dependencies:**
- `fastapi>=0.115.0` - ✅ Recent version, no known critical CVEs
- `uvicorn[standard]>=0.32.0` - ✅ Recent version
- `python-dotenv>=1.0.0` - ✅ Stable, widely used
- `httpx>=0.27.0` - ✅ Recent version
- `pydantic>=2.9.0` - ✅ Pydantic v2, good security track record

**Analysis:**  
No obvious vulnerable dependencies detected. All are maintained and recent versions. Good hygiene with version pinning.

**Recommendations:**
1. Add `safety` or `pip-audit` to check for CVEs: `uv run pip-audit`
2. Consider adding `bandit` for Python security linting
3. Set up Dependabot or Renovate for automated updates
4. Consider pinning exact versions for production deployments

### Frontend Dependencies (package.json)

**Current Dependencies:**
- `react@^19.2.0` - ✅ Latest React 19
- `react-dom@^19.2.0` - ✅ Latest
- `react-markdown@^10.1.0` - ⚠️ Requires security review

**Analysis:**  
`react-markdown` renders user-controlled content. Need to verify:
- XSS protections are enabled
- No unsafe rendering modes used

**Current usage in code:** ✅ Safe - using default secure mode
```jsx
<ReactMarkdown>{msg.content}</ReactMarkdown>
```

`react-markdown` by default escapes HTML and is safe against XSS.

**Recommendations:**
1. Keep React and react-markdown updated
2. Run `npm audit` regularly
3. Consider `npm audit fix` for automated patches
4. Never use `rehype-raw` or `remarkGfm` plugins without sanitization

### Supply Chain Concerns

**Low Risk Areas:**
- Using PyPI and npm official registries
- No suspicious or deprecated packages
- No packages from unknown authors
- All dependencies are popular, well-maintained projects

**Recommendations:**
1. Consider using `pip-audit` or `safety` in CI
2. Add SCA (Software Composition Analysis) tooling
3. Pin exact versions in production (already done in uv.lock)
4. Verify package signatures if deploying to production

---

## Secrets & Configuration Review

### 1. API Key Management

**Finding:** API key stored in `.env` file (not committed, correct), but:
- ❌ No validation that key exists
- ❌ No masking in logs (could leak in error messages)
- ❌ No key rotation guidance
- ✅ Correctly in `.gitignore`
- ✅ Not hardcoded in source

**Recommendation:**
1. Add validation at startup (see Finding #3)
2. Mask API keys in logs: `OPENROUTER_API_KEY[:10]+"..."`
3. Add `.env.example` template:

```bash
# .env.example
# Get your API key from https://openrouter.ai/
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

4. Document key rotation process in README

### 2. Configuration Hardening

**Current State:**
- ✅ `.env` in `.gitignore`
- ✅ `data/` directory in `.gitignore`
- ❌ No environment-specific configs (dev/prod)
- ❌ No secure defaults documented

**Recommendations:**
1. Add environment awareness:
```python
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"
```

2. Add secure production defaults:
```python
if ENVIRONMENT == "production":
    # Require HTTPS in production
    if not os.getenv("FORCE_HTTPS", "").lower() == "true":
        logger.warning("Production mode without HTTPS enforcement")
```

### 3. Sensitive Data in Storage

**Finding:**  
Conversations stored as plain JSON files in `data/conversations/`. These may contain:
- User queries (could be sensitive)
- LLM responses (could quote sensitive input)
- No encryption at rest
- No access controls

**Impact:**  
Anyone with filesystem access can read all conversations.

**Recommendation:**
1. Document that `data/` directory should have restrictive permissions: `chmod 700 data/`
2. Consider encryption at rest for sensitive deployments
3. Add data retention/cleanup utilities
4. Implement conversation export/delete features

### 4. Hardcoded Secrets Scan

**Scan Results:** ✅ No hardcoded secrets found in codebase

Checked for:
- API keys
- Passwords
- Tokens
- Private keys
- Connection strings

---

## CI/CD & Automation Risks

### Current State: No CI/CD

**Finding:**  
No CI/CD pipelines detected:
- ❌ No `.github/workflows/`
- ❌ No automated testing
- ❌ No security scanning
- ❌ No dependency updates

**Impact:**  
- Vulnerabilities won't be detected automatically
- Dependencies will become outdated
- No regression testing
- Manual security reviews required

### Recommendations

**1. Add GitHub Actions for Security**

Create `.github/workflows/security.yml`:
```yaml
name: Security Checks

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install safety bandit pip-audit
          pip install -r <(uv pip compile pyproject.toml)
      
      - name: Run safety check
        run: safety check
      
      - name: Run bandit
        run: bandit -r backend/
      
      - name: Run pip-audit
        run: pip-audit
      
      - name: Run npm audit (frontend)
        working-directory: frontend
        run: npm audit --audit-level=moderate
```

**2. Add Dependabot**

Create `.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
```

**3. Add CodeQL for SAST**

Enable GitHub Advanced Security and CodeQL scanning for Python and JavaScript.

**4. Pre-commit Hooks**

Add `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/PyCQA/bandit
    rev: '1.7.5'
    hooks:
      - id: bandit
        args: ['-c', 'pyproject.toml']
  
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
      - id: check-yaml
      - id: check-json
      - id: detect-private-key
```

---

## Positive Observations

The codebase demonstrates several good security practices:

1. ✅ **Secrets in .gitignore:** API keys are not committed to version control
2. ✅ **Modern Dependencies:** Using recent, maintained versions of libraries
3. ✅ **Pydantic Validation:** Basic input type validation with Pydantic models
4. ✅ **Safe Markdown Rendering:** react-markdown used in safe mode (no HTML)
5. ✅ **Async/Await:** Proper async handling prevents some race conditions
6. ✅ **Graceful Degradation:** Failed model queries don't crash entire request
7. ✅ **CORS Properly Configured:** Specific origins, not wildcard
8. ✅ **No Eval/Exec:** No dangerous dynamic code execution
9. ✅ **Separation of Concerns:** Backend/frontend properly separated
10. ✅ **Clean Code:** Well-structured, readable code reduces bug likelihood

---

## Open Questions / Assumptions

### Questions Requiring Human Judgment

1. **Deployment Model:**  
   - Is this strictly single-user, localhost-only? ✅ Assumed: YES
   - Will it ever be deployed to a network or cloud? ⚠️ If yes, authentication is mandatory

2. **Data Sensitivity:**  
   - What kind of queries will users make? May contain personal/sensitive data?
   - Should conversations be encrypted at rest?
   - What's the data retention policy?

3. **Cost Controls:**  
   - What's the acceptable monthly OpenRouter spend?
   - Should there be hard limits or alerts?
   - Who pays if abused?

4. **Threat Model:**  
   - Are you worried about malicious users, or just bugs?
   - Is physical access to the machine considered secure?
   - Are other users of the same computer trusted?

5. **Compliance Requirements:**  
   - Any GDPR, HIPAA, or other regulatory requirements?
   - Data residency concerns?

### Assumptions Made in This Review

1. **Localhost Deployment:** Assumed application runs locally on single user's machine
2. **Trusted User:** Assumed user running the application is trusted
3. **Private Network:** Assumed any network access is on trusted private network
4. **Development Stage:** Assumed this is a prototype/personal project, not production
5. **No PII:** Assumed conversations don't contain regulated personal information
6. **File System Security:** Assumed host OS has proper file permissions
7. **Python Version:** Assumed Python 3.10+ with standard security patches

### Environment-Specific Validation Needed

1. **OS File Permissions:** Verify `data/` directory has mode 700 (owner-only access)
2. **Firewall Rules:** Confirm port 8001 not exposed to internet
3. **Process Isolation:** Check if backend runs as non-privileged user
4. **Log Access:** Determine who can read application logs (may contain errors with sensitive data)
5. **Backup Strategy:** How are `data/` conversations backed up? Are backups encrypted?

---

## Summary & Prioritized Remediation

### Immediate Actions (Critical & High)

1. **Fix Path Traversal** - Validate conversation IDs (1-2 hours)
2. **Add API Key Validation** - Fail fast if not configured (30 min)
3. **Bind to Localhost** - Change `0.0.0.0` to `127.0.0.1` (5 min)
4. **Add Rate Limiting** - Prevent API abuse (1-2 hours)
5. **Add Input Validation** - Max length checks (1 hour)

### Short-term Actions (Medium)

6. **Improve Error Handling** - Proper logging, no info disclosure (2-3 hours)
7. **Add .env.example** - Help users configure correctly (15 min)
8. **Security Documentation** - Document threat model and safe deployment (1 hour)
9. **Add Request Size Limits** - Prevent memory exhaustion (30 min)

### Long-term Improvements (Low & Nice-to-have)

10. **Add CI/CD Security Scanning** - Automated vulnerability detection (4-6 hours)
11. **Implement Authentication** - If ever networked (1-2 days)
12. **Add Security Tests** - Unit tests for security features (2-4 hours)
13. **Encryption at Rest** - For sensitive deployment scenarios (1 day)
14. **Security Audit Logging** - Track access and modifications (2-4 hours)

---

## Conclusion

LLM Council is a well-structured prototype with **several critical security issues that must be fixed** before any deployment beyond a strictly controlled localhost environment. The path traversal vulnerability is particularly serious and should be addressed immediately.

For personal, localhost use by a single trusted user, the application is **reasonably safe** after fixing the critical issues. For any network deployment or multi-user scenarios, **comprehensive authentication, authorization, and monitoring are mandatory.**

The codebase shows good security awareness (secrets management, modern dependencies, safe rendering) but needs hardening for production use. Priority should be:
1. Fix the critical path traversal
2. Add basic input validation and rate limiting  
3. Improve operational security (logging, monitoring, error handling)
4. Add authentication if ever networked

**Total estimated remediation time for critical/high issues: 6-10 hours**
