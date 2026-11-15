// Window contents for the feature tabs. Data comes from the repo's sample corpus
// (corpus/synthetic/mail-policy-v1/v2.md vs RFC 5321), so every example is one DocuSense really finds.
import type { ReactNode } from "react";

const Call = ({ fn, children }: { fn: string; children?: ReactNode }) => (
  <div className="call">› <span className="fn">{fn}</span>({children})</div>
);
const S = ({ children }: { children: ReactNode }) => <span className="s">{children}</span>;
const Res = ({ h, right, children, faded }: { h: string; right: ReactNode; children?: ReactNode; faded?: boolean }) => (
  <div className={`res ${faded ? "faded" : ""}`}>
    <div className="h"><span>{h}</span>{typeof right === "string" ? <span className="dim">{right}</span> : right}</div>
    {children && <p>{children}</p>}
  </div>
);
const Rule = () => <div className="rule" />;
const Toc = ({ t, n, sub, hl }: { t: string; n: number; sub?: boolean; hl?: boolean }) => (
  <div className={`toc-row ${sub ? "sub" : ""}`}><span className="t">{hl ? <span className="hl">{t}</span> : t}</span><span className="dim">{n}</span></div>
);

/* ---------- #01 read ---------- */

export const tocMock = (
  <>
    <Call fn="get_section_map">doc=<S>&quot;mail-policy&quot;</S></Call>
    <div className="dim">mail-policy@v2 · 6 sections · 1,412 tokens</div>
    <Rule />
    <Toc t="§1 Scope" n={96} />
    <Toc t="§2 Definitions" n={188} />
    <Toc t="§3 Message Limits" n={402} />
    <Toc t="§3.1 Line Length" n={121} sub hl />
    <Toc t="§3.2 Recipients" n={104} sub />
    <Toc t="§3.3 Local-part Length" n={98} sub />
    <Toc t="§4 Delivery Retries" n={231} />
    <Toc t="§5 Command Support" n={142} />
    <Toc t="§6 Transport Security" n={117} />
    <Rule />
    <div className="note">outline only · body not loaded</div>
  </>
);

export const readMock = (
  <>
    <Call fn="read_section">doc=<S>&quot;mail-policy&quot;</S>, section=<S>&quot;3.1&quot;</S></Call>
    <div className="dim">§3.1 Line Length · 121 tokens</div>
    <div className="quote">A message line MUST NOT exceed 1000 octets, including the CRLF, as required by Section 4.5.3.1.6 of RFC 5321.</div>
    <span className="tag ind">ds://mail-policy@v2#§3.1:b812-951</span>
    <Rule />
    <div className="dim">sha256 4be1c9…07af</div>
    <div className="dim">page 2 · span 48</div>
    <Rule />
    <div className="note">121 tokens read · 1,412 in file</div>
  </>
);

const Scored = ({ h, score, children }: { h: string; score: number; children: ReactNode }) => (
  <div className="res">
    <div className="h"><span>{h}</span><span className="dim">{score.toFixed(2)}</span></div>
    <p>{children}</p>
    <div className="meter"><b style={{ width: `${score * 100}%` }} /></div>
  </div>
);

export const searchMock = (
  <>
    <Call fn="search"><S>&quot;how long before we give up delivering&quot;</S></Call>
    <div className="dim">mode=hybrid · bm25 + embeddings · RRF</div>
    <Scored h="mail-policy §4.2" score={0.91}>Undeliverable mail is returned to the sender after 2 days.</Scored>
    <Scored h="rfc5321 §4.5.4.1" score={0.84}>The give-up time generally needs to be at least 4-5 days.</Scored>
    <Scored h="mail-policy §4.1" score={0.52}>The sender SHOULD retry after 15 minutes.</Scored>
  </>
);

export const defMock = (
  <>
    <Call fn="lookup_definition"><S>&quot;Submission server&quot;</S></Call>
    <div className="quote">&quot;Submission server&quot; means an Example Org server that accepts mail from authenticated users.</div>
    <span className="tag ind">ds://mail-policy@v2#§2:b402-497</span>
    <Rule />
    <Call fn="resolve_reference"><S>&quot;Section 4.5.3.1.6 of RFC 5321&quot;</S></Call>
    <Res h="rfc5321 §4.5.3.1.6" right={<span className="tag ok">resolved</span>}>
      The maximum total length of a text line including the &lt;CRLF&gt; is 1000 octets.
    </Res>
  </>
);

/* ---------- #02 cite ---------- */

export const evidenceMock = (
  <>
    <Call fn="get_evidence">span_id=<S>48</S></Call>
    <div className="quote">A message line MUST NOT exceed 1000 octets, including the CRLF.</div>
    <div className="tags"><span className="tag ind">ds://mail-policy@v2#§3.1:b812-951</span><span className="tag ok">✓ verified</span></div>
    <Rule />
    <div className="kv"><span>stored</span><span className="dim">4be1c9d2…a3e107af</span></div>
    <div className="kv"><span>recomputed</span><span className="ok">4be1c9d2…a3e107af</span></div>
    <Rule />
    <div className="kv"><span>version</span><span className="dim">v2 · current</span></div>
    <div className="kv"><span>page</span><span className="dim">2</span></div>
  </>
);

export const packMock = (
  <>
    <Call fn="assemble_context">span_ids=[48,61,77,102], token_budget=<S>1200</S></Call>
    <Rule />
    <Res h="mail-policy §3.1" right="121 tok" />
    <Res h="rfc5321 §4.5.3.1.6" right="288 tok" />
    <Res h="mail-policy §3.2" right="104 tok" />
    <Res h="rfc5321 §4.5.3.1.8" right="dropped" faded />
    <Rule />
    <div className="kv"><span>budget</span><span>513 / 1,200</span></div>
    <div className="meter"><b style={{ width: "43%" }} /></div>
  </>
);

export const tamperMock = (
  <>
    <Call fn="verify_span">span_id=<S>48</S>, deep=<S>true</S></Call>
    <Res h="mail-policy §3.1" right={<span className="tag ok">✓ verified</span>}>hash matches stored bytes and source file</Res>
    <Rule />
    <div className="dim">agent quoted:</div>
    <div className="quote red">&quot;Message lines MAY be up to 2000 octets.&quot;</div>
    <Res h="not found in v2" right={<span className="tag bad">✗ unverified</span>}>
      Closest match is v1 §3.1 (superseded). Don&apos;t cite it as current.
    </Res>
  </>
);

/* ---------- #03 versions ---------- */

export const diffMock = (
  <>
    <Call fn="diff_versions">doc=<S>&quot;mail-policy&quot;</S></Call>
    <div className="dim">v1 → v2 · 4 changed · 1 added</div>
    <Rule />
    <div className="dim">§3.1 Line Length</div>
    <span className="d-del">− A message line MAY be up to 2000 octets</span>
    <span className="d-add">+ A message line MUST NOT exceed 1000 octets</span>
    <div className="d-sec">§3.2 Recipients</div>
    <span className="d-del">− MUST NOT accept more than 50 recipients</span>
    <span className="d-add">+ MUST accept at least 100 recipients</span>
    <div className="d-sec">§6 Transport Security</div>
    <span className="d-add">+ A relay server MUST offer STARTTLS</span>
  </>
);

export const blameMock = (
  <>
    <Call fn="blame">text=<S>&quot;retry after 15 minutes&quot;</S></Call>
    <Rule />
    <Res h="v2 · §4.1" right={<span className="tag ok">current</span>}>When delivery fails temporarily, the sender SHOULD retry after 15 minutes.</Res>
    <Res h="v1 · §4.1" right={<span className="tag ind">superseded</span>}>When delivery fails temporarily, the sender SHOULD retry after 10 minutes.</Res>
    <Rule />
    <div className="note">introduced in v2 · changed 10 → 15 min</div>
  </>
);

export const conflictMock = (
  <>
    <Call fn="find_contradictions">doc=<S>&quot;mail-policy&quot;</S></Call>
    <div className="vs">
      <div className="side"><div className="src">mail-policy@v2 §4.2</div><p>Undeliverable mail is returned after <b>2 days</b>.</p></div>
      <div className="versus">VALUE MISMATCH</div>
      <div className="side"><div className="src">smtp@rfc5321 §4.5.4.1</div><p>The give-up time needs to be at least <b>4-5 days</b>.</p></div>
    </div>
    <div className="note" style={{ marginTop: 10 }}>both sides cited · no winner picked</div>
  </>
);

export const affectedMock = (
  <>
    <Call fn="find_affected_documents">doc=<S>&quot;rfc5321&quot;</S></Call>
    <Rule />
    <Res h="mail-policy@v2" right="5 refs">§3.1, §3.2, §4.1, §4.2, §5</Res>
    <Res h="relay-runbook@v3" right="2 refs">§2.4, §7</Res>
    <Res h="onboarding-guide@v1" right="1 ref">§9.2</Res>
  </>
);
