# Example Org Mail Server Policy

> SYNTHETIC TEST DOCUMENT. "Example Org" is fictional. This policy deliberately conflicts with
> RFC 5321 in places so that DocuSense contradiction detection can be evaluated.

Version: 1.0
Status: Superseded

## 1. Scope

This policy applies to every SMTP server operated by Example Org, including inbound relays and
outbound submission servers. The key words "MUST", "MUST NOT", "SHOULD" and "MAY" are to be
interpreted as described in RFC 2119.

## 2. Definitions

"Relay server" means any Example Org SMTP server that accepts mail for delivery to another host.

"Message line" means a sequence of characters in the message content terminated by CRLF.

## 3. Message Limits

### 3.1 Line Length

A message line MAY be up to 2000 octets long, including the CRLF.

### 3.2 Recipients

A relay server MUST NOT accept more than 50 recipients for a single message.

### 3.3 Local-part Length

The local-part of a mailbox address MUST NOT exceed 64 octets.

## 4. Delivery Retries

### 4.1 Retry Interval

When delivery fails temporarily, the sender SHOULD retry after 10 minutes.

### 4.2 Give-up Time

Undeliverable messages MUST be returned to the sender after 2 days.

## 5. Command Support

A relay server MUST NOT support the VRFY command.
