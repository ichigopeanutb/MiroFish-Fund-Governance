# Operator Checklist - 從 Intake 到 Simulation

這份 checklist 是給 operator 使用，不是給非技術 reviewer 填寫。目標是把 intake form 轉成可跑的 synthetic simulation setup，並保持資料邊界乾淨。

## 0. Pre-Check

- [ ] Intake form 沒有真實 LP 名單。
- [ ] 沒有銀行資訊、稅務紀錄、完整法律文件或投資人身份。
- [ ] 所有 fund name / LP name / company name 已匿名化或改成 synthetic。
- [ ] Reviewer 主要問題已明確。
- [ ] Desired output 已選定：report / meeting pack / decision memo / LP update。

如果有敏感資料，先要求對方改寫成匿名摘要，不要放進 repo 或 simulation input。

## 1. Map Intake To Simulation Setup

| Intake Item | Simulation Field |
| --- | --- |
| Fund stage | fund lifecycle state |
| Fund size / target size | commitment base |
| Strategy | portfolio scenario assumptions |
| Management fee / carry / hurdle | fund terms |
| LPAC consent items | governance rules |
| Event type | simulation event branch |
| Amount involved | cashflow event |
| Main risk | risk appendix |
| Desired output | report template section emphasis |

## 2. Choose Simulation Mode

- [ ] LP communication rehearsal.
- [ ] IC / LPAC decision rehearsal.
- [ ] Capital call / unfunded commitment check.
- [ ] Waterfall / distribution explanation.
- [ ] Follow-on reserve / bridge / down round scenario.
- [ ] Exit / partial exit / delayed exit scenario.

## 3. Build Synthetic Names

Use neutral names:

- Fund: Fund I / Fund II / Synthetic Growth Fund.
- LP: LP-A / LP-B / Anchor LP.
- Portfolio company: PortfolioCo-A / PortfolioCo-B.
- Decision body: IC / LPAC / GP Committee.

Do not use real names unless a formal data handling process exists.

## 4. Prepare Simulation Notes

Create a short operator note:

```text
Simulation purpose:
Reviewer role:
Scenario:
Main questions:
Synthetic assumptions:
Excluded sensitive information:
Expected output:
```

## 5. Run And Review

- [ ] Run synthetic simulation.
- [ ] Check ledger balance.
- [ ] Check capital called / paid / unfunded commitment.
- [ ] Check governance decisions and required approvals.
- [ ] Check risk appendix.
- [ ] Check whether output answers the reviewer questions.
- [ ] Remove any accidental sensitive text before sending.

## 6. Delivery

Send only:

- Chinese output report / meeting pack PDF.
- Short note asking for three reactions.

Do not send:

- GitHub repo.
- Raw simulation config.
- Access code.
- Internal operator notes.
- Any unreviewed generated output.
