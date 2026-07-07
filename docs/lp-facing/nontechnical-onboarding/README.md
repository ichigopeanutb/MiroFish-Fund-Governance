# Nontechnical Fund Manager Onboarding Workflow

這個資料夾是給「沒有技術人員協助的基金經理人 / GP / LP-facing reviewer」使用的服務式 onboarding 流程。

目標不是讓對方 clone repo 或自己操作系統，而是讓對方用最少負擔提供一個簡化情境，然後由 operator 代為轉成 MiroFish Fund Governance Edition 的 simulation input，最後交付一份中文 report / meeting pack。

## Roadmap Fit Check

這個 milestone 目前是正確的，因為現階段真正的 adoption bottleneck 不是 GitHub 是否公開，而是非技術基金經理人是否能在沒有工程支援的情況下理解並取得價值。

目前應優先驗證：

- 基金經理人是否願意提供一個簡化情境讓你代跑。
- 他們在意的是 LP 溝通、capital call、waterfall、IC / LPAC、還是 meeting pack。
- 一份中文 output report 是否足以讓他們進入第二次對話。
- 哪些資料欄位會讓他們覺得太敏感或太麻煩。

## Recommended Flow

1. 先發中文版 PDF 介紹包。
2. 如果對方有興趣，不給 GitHub，改給 intake form。
3. 對方只填簡化/匿名/合成情境。
4. Operator 用 checklist 將情境轉成 simulation setup。
5. 跑 synthetic simulation。
6. 交付中文 report / meeting pack。
7. 收三個 feedback：
   - 哪一部分有用？
   - 哪一部分不像真實基金運作？
   - 下一次要補哪個 workflow？

## Files

- [中文 Intake Form](./fund-manager-intake-form-zh.md)
- [Operator Checklist](./operator-checklist-zh.md)
- [中文 Output Report Template](./output-report-template-zh.md)

## Data Boundary

不要請對方提供真實 LP 名單、投資人身份、銀行資訊、稅務紀錄、法律意見、完整 LPA、side letter 原文或任何不可公開的基金文件。

早期 intake 應該只收：

- 匿名化 fund profile。
- 簡化 fund terms。
- 合成或概括化 capital event。
- reviewer 想驗證的 governance question。
- 對 LP / IC / LPAC 溝通最擔心的問題。
