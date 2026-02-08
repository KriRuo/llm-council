# Security Policy

## Supported Versions

This project is currently in early development. Security updates will be applied to the latest version only.

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < latest| :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in LLM Council, please report it by:

1. **DO NOT** open a public GitHub issue
2. Email the maintainer or use GitHub's private security advisory feature
3. Provide detailed information about the vulnerability:
   - Description of the issue
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Considerations

### Deployment Model

**LLM Council is designed for single-user, localhost-only deployment.**

⚠️ **Important Security Warnings:**

- This application has **NO authentication** by default
- It binds to `127.0.0.1` (localhost only) for security
- **Do NOT expose it to a network** without adding proper authentication
- Conversations are stored in plain text JSON files
- Anyone with filesystem access can read your conversations

### For Network Deployment

If you must deploy this to a network (not recommended without modifications):

1. ✅ **REQUIRED:** Implement authentication (OAuth2, API keys, etc.)
2. ✅ **REQUIRED:** Use HTTPS with valid TLS certificates
3. ✅ **REQUIRED:** Set up a reverse proxy (nginx, Caddy)
4. ✅ **REQUIRED:** Review the rate limiting configuration
5. ✅ **RECOMMENDED:** Implement per-user API key management
6. ✅ **RECOMMENDED:** Add logging and monitoring
7. ✅ **RECOMMENDED:** Encrypt conversations at rest

### Security Features

Current security features include:

- ✅ Path traversal protection with UUID validation
- ✅ Input validation and sanitization (50KB max message size)
- ✅ Rate limiting (10 requests/minute for messages)
- ✅ API key validation on startup
- ✅ Localhost-only binding by default
- ✅ Secure error handling (no information disclosure)
- ✅ Dependency security scanning (via GitHub Actions)

### Known Limitations

- ❌ No authentication or authorization
- ❌ No encryption at rest for conversations
- ❌ No audit logging
- ❌ No user management
- ❌ No session management
- ❌ Designed for trusted, single-user environments only

## Security Review

A comprehensive security review is available in `SECURITY_REVIEW.md`. This document contains:

- Detailed vulnerability analysis
- Risk assessments
- Remediation recommendations
- Best practices for deployment

Review this document before deploying to any environment.

## Dependencies

We use automated tools to keep dependencies secure:

- **Dependabot:** Automatically creates PRs for dependency updates
- **GitHub Actions:** Runs security scans on every push
  - `safety` - Python CVE scanning
  - `bandit` - Python security linting
  - `pip-audit` - Dependency vulnerability scanning
  - `npm audit` - JavaScript dependency scanning

## Best Practices

When using LLM Council:

1. **Keep API keys secure:**
   - Never commit `.env` file
   - Use strong, unique API keys
   - Rotate keys regularly
   - Restrict API key permissions when possible

2. **Protect conversation data:**
   - Set restrictive file permissions: `chmod 700 data/`
   - Back up conversations securely
   - Delete old conversations periodically
   - Consider encrypting backups

3. **Monitor usage:**
   - Check OpenRouter billing regularly
   - Monitor for unusual activity
   - Review logs for errors

4. **Keep software updated:**
   - Update dependencies regularly
   - Monitor security advisories
   - Apply patches promptly

## License

See LICENSE file for details.
