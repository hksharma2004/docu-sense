# Example Org Mail Server Policy

> SYNTHETIC TEST DOCUMENT. "Example Org" is fictional. This policy deliberately conflicts with
> RFC 5321 in places so that DocuSense contradiction detection can be evaluated.

Version: 2.0
Status: Current

## 1. Scope

This policy applies to every SMTP server operated by Example Org, including inbound relays and
outbound submission servers. The key words "MUST", "MUST NOT", "SHOULD" and "MAY" are to be
interpreted as described in RFC 2119.

## 2. Definitions

"Relay server" means any Example Org SMTP server that accepts mail for delivery to another host.

"Message line" means a sequence of characters in the message content terminated by CRLF.

"Submission server" means an Example Org server that accepts mail from authenticated users.

## 3. Message Limits

### 3.1 Line Length

A message line MUST NOT exceed 1000 octets, including the CRLF, as required by Section 4.5.3.1.6
of RFC 5321.

### 3.2 Recipients

A relay server MUST accept at least 100 recipients for a single message.

### 3.3 Local-part Length

The local-part of a mailbox address MUST NOT exceed 64 octets.

## 4. Delivery Retries

### 4.1 Retry Interval

When delivery fails temporarily, the sender SHOULD retry after 15 minutes.

### 4.2 Give-up Time

Undeliverable messages MUST be returned to the sender after 2 days.

## 5. Command Support

A relay server MUST NOT support the VRFY command.

## 6. Transport Security

A relay server MUST offer the STARTTLS extension. A submission server MUST NOT accept
credentials before TLS has been negotiated.
