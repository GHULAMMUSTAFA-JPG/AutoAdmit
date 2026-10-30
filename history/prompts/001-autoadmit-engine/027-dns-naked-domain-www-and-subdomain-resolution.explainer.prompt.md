---
id: "027"
title: "Technical Explanation of Naked Domain DNS vs WWW and Pinyin Subdomain Resolution"
stage: "explainer"
date_iso: "2026-10-31"
surface: "agent"
model: "gemini-2.5-pro"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "User"
command: "/sp.explainer"
labels: ["dns", "www", "subdomains", "crawling", "whpu", "architecture"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0002-multi-source-discovery-and-truthfulness-pipeline.md"
  pr: null
files_yaml: []
tests_yaml: []
---

### Prompt Text
same with jsj.whpu.edu.cn (计算机学院 - School of Computer Science)
scse.whpu.edu.cn (School of Computer Science & Engineering), https://www.whpu.edu.cn/jsj/ gone to a uni page with(https://www.whpu.edu.cn/xygk/szdw.htm) which redirected it to homapage both link s, explain now what and links when added like https://www.whpu.edu.cn/ so links require www. give me short explaantion

### Key Decisions & Actions
- Investigated live network records of `whpu.edu.cn` to verify DNS and routing behavior.
- Confirmed that Wuhan Polytechnic University does not configure a DNS A record on the apex domain (`whpu.edu.cn`), requiring `www.whpu.edu.cn`.
- Traced the real Computer Science department through the official schools directory (`/jgsz/yxsz.htm`) to `http://sjxy.whpu.edu.cn/` (数学与计算机学院, School of Mathematics and Computer Science).
- Traced the real supervisor directory to `http://sjxy.whpu.edu.cn/yjsjy/dsdw_new.htm`.
- Delivered short, clear explanation addressing: (1) why naked domains fail without `www.`, (2) why guessing subdomains fails, and (3) why homepage redirects occur.

