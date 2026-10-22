# Example Org OAuth Deployment Profile

> SYNTHETIC TEST DOCUMENT. "Example Org" is fictional. This profile deliberately conflicts with
> RFC 6749, RFC 7636 and RFC 9700 in places so that DocuSense contradiction detection can be
> evaluated.

Version: 1.0
Status: Current

## 1. Scope

This profile describes how Example Org applications use OAuth 2.0 as defined in RFC 6749. The
key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT" and "MAY" are to be interpreted as described
in RFC 2119.

## 2. Grant Types

### 2.1 Implicit Grant

Single-page applications MAY use the implicit grant.

### 2.2 Authorization Code Grant

Server-side applications MUST use the authorization code grant.

## 3. PKCE

### 3.1 When PKCE Is Required

PKCE is OPTIONAL for confidential clients.

### 3.2 Code Verifier Length

The code_verifier MUST be at least 32 characters long.

## 4. Authorization Codes

An authorization code MAY remain valid for up to 30 minutes.

## 5. Redirect URIs

The authorization server MAY use prefix matching when comparing redirect URIs against
registered values.

| Client type      | Allowed grants              |
|------------------|-----------------------------|
| Single-page app  | implicit, authorization code |
| Server-side app  | authorization code          |
| Native app       | authorization code          |
