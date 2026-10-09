# Part 2 test: actual (read from the image) vs pipeline output

Images tested: **57** (`2-p1.jpeg` is a Part 1 page: expected no rows and no summary). Values compared: **1937**.

| Result | Count | % |
|---|---|---|
| Exact match | 1322 | 68.2% |
| Same value, only spaces/punctuation, Ø-vs-0 or HSN 3-vs-8 differ | 338 | 17.4% |
| Real difference | 277 | 14.3% |
| Correct ignoring cosmetics | 1660 | 85.7% |

- Line-item rows in the images: **249**; pipeline returned **243**; matched **240**.
- Documents with the exact number of rows: **52/57**; tax summary fully right: **54/57**; every value right: **13/57**.

## Per field

| Field | Exact | Cosmetic | Real | Right ignoring cosmetics |
|---|---|---|---|---|
| srNo | 145 | 0 | 91 | 61.4% |
| description | 5 | 140 | 104 | 58.2% |
| hsnSac | 45 | 191 | 13 | 94.8% |
| basic | 230 | 0 | 19 | 92.4% |
| quantity | 230 | 0 | 19 | 92.4% |
| amount | 221 | 0 | 28 | 88.8% |
| cgstRate | 57 | 0 | 0 | 100.0% |
| cgstAmount | 57 | 0 | 0 | 100.0% |
| sgstRate | 57 | 0 | 0 | 100.0% |
| sgstAmount | 57 | 0 | 0 | 100.0% |
| igstRate | 56 | 0 | 1 | 98.2% |
| igstAmount | 54 | 2 | 1 | 98.2% |
| totalBasicAmount | 54 | 2 | 1 | 98.2% |
| totalAmount | 54 | 3 | 0 | 100.0% |

## Per image

| Image | Rows (actual/OCR) | Real diffs in rows | Real diffs in tax summary | Multi-page flag |
|---|---|---|---|---|
| 1-p2.jpeg | 5/5 | 7 | 1 | False |
| 2-p1.jpeg | 0/0 | 0 | 0 | False |
| 2-p2.jpeg | 3/3 | 5 | 0 | False |
| 3-p2.jpeg | 10/10 | 12 | 1 | True |
| 4-p2.jpeg | 3/3 | 6 | 0 | False |
| 5-p2.jpeg | 7/7 | 11 | 0 | True |
| 6-p2.jpeg | 11/10 | 16 | 0 | True |
| 7-p2.jpeg | 1/1 | 1 | 0 | False |
| 8-p2.jpeg | 1/1 | 1 | 0 | False |
| 9-p2.jpeg | 4/4 | 5 | 0 | False |
| 10-p2.jpeg | 4/4 | 8 | 0 | False |
| 11-p2.jpeg | 6/6 | 6 | 0 | False |
| 12-p2.jpeg | 5/5 | 5 | 0 | False |
| 13-p2.jpeg | 2/2 | 1 | 0 | False |
| 14-p2.jpeg | 5/5 | 0 | 0 | False |
| 15-p2.jpeg | 15/15 | 37 | 0 | False |
| 16-p2.jpeg | 4/4 | 2 | 0 | False |
| 17-p2.jpeg | 2/2 | 0 | 0 | False |
| 18-p2.jpeg | 2/2 | 0 | 0 | False |
| 19-p2.jpeg | 5/4 | 8 | 0 | False |
| 20-p2.jpeg | 6/6 | 10 | 0 | False |
| 21-p2.jpeg | 2/0 | 2 | 0 | False |
| 22-p2.jpeg | 5/5 | 4 | 0 | False |
| WhatsApp Image 2026-08-01 at 01.29.16.jpeg | 2/2 | 0 | 0 | False |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | 6/6 | 5 | 0 | False |
| WhatsApp Image 2026-08-01 at 01.29.18.jpeg | 1/1 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.19 (1).jpeg | 5/5 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.19.jpeg | 1/1 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (1).jpeg | 5/5 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (10).jpeg | 1/1 | 3 | 1 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (11).jpeg | 2/2 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (12).jpeg | 1/1 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (13).jpeg | 3/3 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (14).jpeg | 6/6 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (15).jpeg | 5/5 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (16).jpeg | 2/2 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | 6/6 | 5 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (18).jpeg | 1/0 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (19).jpeg | 5/5 | 4 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (2).jpeg | 5/5 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (20).jpeg | 5/5 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (21).jpeg | 4/4 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (22).jpeg | 4/4 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (23).jpeg | 4/4 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (24).jpeg | 4/4 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (25).jpeg | 6/6 | 4 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (26).jpeg | 8/8 | 4 | 0 | True |
| WhatsApp Image 2026-10-08 at 00.35.20 (27).jpeg | 1/1 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | 6/6 | 6 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (4).jpeg | 2/2 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | 7/7 | 20 | 0 | True |
| WhatsApp Image 2026-10-08 at 00.35.20 (6).jpeg | 3/3 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (7).jpeg | 2/2 | 0 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | 7/6 | 7 | 0 | True |
| WhatsApp Image 2026-10-08 at 00.35.20 (9).jpeg | 1/1 | 1 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.20.jpeg | 5/5 | 2 | 0 | False |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | 15/15 | 6 | 0 | True |

## All real differences (235)

| Image | Where | Field | Actual | OCR |
|---|---|---|---|---|
| 1-p2.jpeg | row 2 | srNo | 2 | None |
| 1-p2.jpeg | row 2 | description | HOB ED23167(43875) Ø90x140-A | HOEED2316743875)90x140-A |
| 1-p2.jpeg | row 3 | srNo | 3 | None |
| 1-p2.jpeg | row 4 | srNo | 4 | None |
| 1-p2.jpeg | row 5 | srNo | 5 | None |
| 1-p2.jpeg | row 5 | amount | 8,000.00 | 8.000.00 |
| 1-p2.jpeg | row 6 | srNo | 6 | None |
| 1-p2.jpeg | summary | igstRate | 18.00 | 13.00 |
| 2-p2.jpeg | row 2 | srNo | 2 | None |
| 2-p2.jpeg | row 3 | srNo | 3 | None |
| 2-p2.jpeg | row 3 | description | SHANK HOB ED23115(NG860) Ø60X290-AA | SHANK HOB ED23115(NG860)60X2S0-AA |
| 2-p2.jpeg | row 4 | srNo | 4 | None |
| 2-p2.jpeg | row 4 | description | GSC ED3103(133602) Ø145x36 | GSCED3103(133602)0145x36 |
| 3-p2.jpeg | row 2 | srNo | 2 | None |
| 3-p2.jpeg | row 2 | hsnSac | 993729 | 999729 |
| 3-p2.jpeg | row 3 | srNo | 3 | None |
| 3-p2.jpeg | row 4 | srNo | 4 | None |
| 3-p2.jpeg | row 4 | description | SC DRILL Ø9.0xFL61xOAL103-SANDVIK | SCDRILL9.0xFL61xOAL103-SANDVI |
| 3-p2.jpeg | row 5 | srNo | 5 | None |
| 3-p2.jpeg | row 6 | srNo | 6 | E |
| 3-p2.jpeg | row 7 | srNo | 7 | None |
| 3-p2.jpeg | row 7 | basic | 1,400.00 | 1,40000 |
| 3-p2.jpeg | row 8 | srNo | 8 | None |
| 3-p2.jpeg | row 9 | srNo | 9 | P |
| 3-p2.jpeg | row 11 | srNo | 11 | 1T |
| 3-p2.jpeg | summary | totalBasicAmount | 28,900.00 | 28200.00 |
| 4-p2.jpeg | row 2 | srNo | 2 | 5 |
| 4-p2.jpeg | row 2 | description | SHANK GSC ED32226(159258) Ø42X127 | SHANKG5CED32226(159258)42X127 |
| 4-p2.jpeg | row 2 | amount | 10,000.00 | None |
| 4-p2.jpeg | row 3 | srNo | 3 | None |
| 4-p2.jpeg | row 4 | srNo | 4 | None |
| 4-p2.jpeg | row 4 | description | SHANK GSC ED1344(164296) Ø28X112 | SHANKGSCED1344(164296)028X112 |
| 5-p2.jpeg | row 2 | srNo | 2 | 7 |
| 5-p2.jpeg | row 3 | description | SC STEP DRILL Ø8.97xFL44xOAL90-KCT | SC STEP DRILL8.97xFL44xOAL90-KC |
| 5-p2.jpeg | row 4 | srNo | 4 | C |
| 5-p2.jpeg | row 4 | quantity | 1 | 7 |
| 5-p2.jpeg | row 4 | amount | 800.00 | $00.00 |
| 5-p2.jpeg | row 5 | srNo | 5 | None |
| 5-p2.jpeg | row 6 | srNo | 6 | None |
| 5-p2.jpeg | row 6 | description | SC DRILL Ø13.6xFL70xOAL136-SUMITOMO | 5CDRILL13.6xFL70xOAL136-SUMITOMO |
| 5-p2.jpeg | row 7 | srNo | 7 | None |
| 5-p2.jpeg | row 8 | srNo | 8 | None |
| 5-p2.jpeg | row 8 | description | STEP ENDMILL Ø13.75x15°xFL60xOAL107-WOLF | STEP ENDMILL013.75x15xFL60xOAL07-WOLF |
| 6-p2.jpeg | row 11 | ROW MISSING | STEP ENDMILL Ø13.75x15°xFL60xOAL107-WOLF | (not extracted) |
| 6-p2.jpeg | row 12 | ROW MISSING | ENDMILL Ø20xFL50xOAL105-India Tools | (not extracted) |
| 6-p2.jpeg | row 2 | srNo | 2 | None |
| 6-p2.jpeg | row 2 | amount | 1,800.00 | 1,300.00 |
| 6-p2.jpeg | row 3 | srNo | 3 | - |
| 6-p2.jpeg | row 3 | description | SC STEP DRILL Ø8.95xFL44xOAL90-OM TECH | SC STEPDRILL8.95xFL44xOAL90-OM1 TECH |
| 6-p2.jpeg | row 4 | srNo | 4 | 0 |
| 6-p2.jpeg | row 4 | description | SC DRILL Ø9.0xFL61xOAL103-SANDVIK | SCDRILL9.0xFL61xOAL103-SANDVK |
| 6-p2.jpeg | row 5 | description | SC DRILL Ø11.1xFL50xOAL100-CERATIZIT | SCDRILL11.1xFL50xOAL100-CERATZIT |
| 6-p2.jpeg | row 6 | srNo | 6 | 8 |
| 6-p2.jpeg | row 7 | srNo | 7 | A |
| 6-p2.jpeg | row 7 | description | SC DRILL Ø17.0xFL73xOAL123-SANDVIK | SCDRILL17.0xFL73xOAL123-SAND1K |
| 6-p2.jpeg | row 8 | description | SC REAMER Ø5.98xFL35xOAL79-WOLF | SC REAMER5.98xFL35xOAL79-WOLI |
| 6-p2.jpeg | row 9 | srNo | 9 | . |
| 6-p2.jpeg | row 9 | description | SC ENDMILL Ø9.35xFL55xOAL100-BARGIR | 5C ENDMILL09.35xFL55xOAL100-BARGIR |
| 6-p2.jpeg | - | EXTRA ROW | (none) | END / None |
| 7-p2.jpeg | row 2 | srNo | 2 | A |
| 8-p2.jpeg | row 2 | srNo | 2 | None |
| 9-p2.jpeg | row 3 | srNo | 3 | None |
| 9-p2.jpeg | row 3 | description | GSC ED3102(130400) Ø150x11 | GSCED3102(130400)0150x11 |
| 9-p2.jpeg | row 4 | srNo | 4 | None |
| 9-p2.jpeg | row 5 | srNo | 5 | None |
| 9-p2.jpeg | row 5 | description | SHANK GSC ED3115(157730) Ø22x80 | SHANKGSCED3115(157730)022x80 |
| 10-p2.jpeg | row 2 | srNo | 2 | None |
| 10-p2.jpeg | row 2 | description | HOB ED27135(RB653) Ø90X106-AA | HO8ED27135(RB653)090X106-AA |
| 10-p2.jpeg | row 3 | srNo | 3 | None |
| 10-p2.jpeg | row 3 | description | HOB ED0861(166373) Ø90X140-A | HOEED0861(166373)090X140-A |
| 10-p2.jpeg | row 4 | srNo | 4 | None |
| 10-p2.jpeg | row 4 | description | HOB ED23404(175704) Ø90X140-A | HOBED23404(175704)090X140-A |
| 10-p2.jpeg | row 5 | srNo | 5 | None |
| 10-p2.jpeg | row 5 | description | HOB ED20189(151421) Ø90X140-A | HOBED29189(151421)090x140-A |
| 11-p2.jpeg | row 2 | description | HOB ED0836(144549) Ø95X150-A | HOBED0836(144549)095X150-A |
| 11-p2.jpeg | row 4 | description | HOB ED3102(119386) Ø75x100-A | HOB ED3102(119386075x100-A |
| 11-p2.jpeg | row 5 | description | HOB ED27137(180992) Ø90x140-AA | HOBED27137(180992)090x140-AA |
| 11-p2.jpeg | row 6 | description | HOB ED32264(144491) Ø95X150-A | HOB ED32264(144491)095X150-A |
| 11-p2.jpeg | row 7 | srNo | 7 | None |
| 11-p2.jpeg | row 7 | description | HOB ED2721(PA525) Ø80X124-AA | HOB ED2721(PA525)080X124-AA |
| 12-p2.jpeg | row 2 | srNo | 2 | None |
| 12-p2.jpeg | row 4 | description | HOB ED2714(RC931) Ø90x140-AA | HIOBED2714(RC931)90x140-AA |
| 12-p2.jpeg | row 4 | quantity | 1 | None |
| 12-p2.jpeg | row 4 | amount | 13,000.00 | L 13,000.00 |
| 12-p2.jpeg | row 5 | description | HOB ED10378(169229) Ø90X140-A | HOBED10378(169229)090X140-A |
| 13-p2.jpeg | row 3 | description | GSC ED32165(26694) Ø183x43 | GSC ED32165(26694)0183x43 |
| 15-p2.jpeg | row 15 | ROW MISSING | HOB ED53144(ME425) Ø90x180 | (not extracted) |
| 15-p2.jpeg | row 16 | ROW MISSING | HOB ED24125(180053) Ø70x170 | (not extracted) |
| 15-p2.jpeg | row 2 | srNo | 2 | 5 |
| 15-p2.jpeg | row 2 | description | HOB ED24126(RB976) Ø70x170 | HOB ED24116(179491)70x170 |
| 15-p2.jpeg | row 3 | srNo | 3 | 9 |
| 15-p2.jpeg | row 3 | description | HOB ED2482(PE553) Ø70x170 | HOB ED24178(PM647)70x120 |
| 15-p2.jpeg | row 4 | srNo | 4 | 13 |
| 15-p2.jpeg | row 4 | description | HOB ED24115(158523) Ø70x170 | HOBED24178(PP146)70x120 |
| 15-p2.jpeg | row 5 | srNo | 5 | 6 |
| 15-p2.jpeg | row 5 | description | HOB ED24116(179491) Ø70x170 | HOBED2452(128577)070x150 |
| 15-p2.jpeg | row 6 | srNo | 6 | 11 |
| 15-p2.jpeg | row 6 | description | HOB ED2452(128577) Ø70x150 | HOBED6634(47713)090x120 |
| 15-p2.jpeg | row 8 | description | HOB ED70122(75129) Ø90x100-A | HOB ED70122(75129)090x100-A |
| 15-p2.jpeg | row 9 | srNo | 9 | 10 |
| 15-p2.jpeg | row 9 | description | HOB ED24178(PM647) Ø70x120 | HOBED53196(163831)90x140 |
| 15-p2.jpeg | row 10 | srNo | 10 | 12 |
| 15-p2.jpeg | row 10 | description | HOB ED53196(163831) Ø90x140 | HOBED56339(152080)90x140 |
| 15-p2.jpeg | row 10 | basic | 5,000.00 | 5,500.00 |
| 15-p2.jpeg | row 10 | amount | 5,000.00 | 5,500.00 |
| 15-p2.jpeg | row 11 | srNo | 11 | 15 |
| 15-p2.jpeg | row 11 | description | HOB ED6634(47713) Ø90x120 | HOB ED53144(ME425)90x180 |
| 15-p2.jpeg | row 11 | basic | 5,000.00 | 6,000.00 |
| 15-p2.jpeg | row 11 | amount | 5,000.00 | 6,000.00 |
| 15-p2.jpeg | row 12 | srNo | 12 | 14 |
| 15-p2.jpeg | row 12 | description | HOB ED56339(152080) Ø90x140 | HOBED63212(106122)90x140 |
| 15-p2.jpeg | row 12 | basic | 5,500.00 | 6,000.00 |
| 15-p2.jpeg | row 12 | amount | 5,500.00 | 6,000.00 |
| 15-p2.jpeg | row 13 | srNo | 13 | 2 |
| 15-p2.jpeg | row 13 | description | HOB ED24178(PP146) Ø70x120 | HOB ED24126(RB976)70x170 |
| 15-p2.jpeg | row 13 | basic | 5,500.00 | 5,000.00 |
| 15-p2.jpeg | row 13 | amount | 5,500.00 | None |
| 15-p2.jpeg | row 14 | srNo | 14 | 16 |
| 15-p2.jpeg | row 14 | description | HOB ED63212(106122) Ø90x140 | HOBED2412518005370x170 |
| 15-p2.jpeg | row 14 | basic | 6,000.00 | 6,500.00 |
| 15-p2.jpeg | row 14 | amount | 6,000.00 | 6,500.00 |
| 15-p2.jpeg | - | EXTRA ROW | (none) | 5,000.00 / 1 |
| 15-p2.jpeg | - | EXTRA ROW | (none) | 5,000.00 / 5,500.00 |
| 16-p2.jpeg | row 4 | description | CARBIDE HOB ED24127(N2834) Ø70x170 | CARBIDEHOBED24127(N2834)070x170 |
| 16-p2.jpeg | row 5 | description | CARBIDE HOB ED24127(P3270) Ø70x170 | CARBIDE HOBED24127(P3270)070x170 |
| 19-p2.jpeg | row 6 | ROW MISSING | GSCED-10258-168248-RESHARPNING & RECOAT | (not extracted) |
| 19-p2.jpeg | row 2 | srNo | 2 | 2, |
| 19-p2.jpeg | row 2 | description | GSCED-10154-167327 | GSCED-10154-167327 15843 |
| 19-p2.jpeg | row 3 | srNo | 3 | 3, |
| 19-p2.jpeg | row 3 | description | GSCED-5319-25627 | GSCED-5319-25627 1705 |
| 19-p2.jpeg | row 4 | description | GSCED-5645-17641 | GSCED-5645-17641 153428 |
| 19-p2.jpeg | row 5 | srNo | 5 | 5- |
| 19-p2.jpeg | row 5 | description | GSCED-1019-18545 | GSCED-1019-18545 144 438 |
| 20-p2.jpeg | row 2 | srNo | 2 | None |
| 20-p2.jpeg | row 3 | srNo | 3 | None |
| 20-p2.jpeg | row 3 | amount | 2,400.00 | 400.00 |
| 20-p2.jpeg | row 4 | srNo | 4 | None |
| 20-p2.jpeg | row 4 | description | SC DRILL Ø13.6xFL70xOAL136-SUMITOMO | SCDRILL13.6xFL70xOAL136-5UMITOMO |
| 20-p2.jpeg | row 5 | srNo | 5 | None |
| 20-p2.jpeg | row 6 | srNo | 6 | None |
| 20-p2.jpeg | row 6 | hsnSac | 993729 | 999729 |
| 20-p2.jpeg | row 7 | srNo | 7 | None |
| 20-p2.jpeg | row 7 | description | STEP ENDMILL Ø13.75x15°xFL60xOAL107-WOLF | STEP ENDMILL013.75x15xFL60xOAL107-WOLF |
| 21-p2.jpeg | row 2 | ROW MISSING | SC DRILL Ø13.6xFL70xOAL136-SUMITOMO | (not extracted) |
| 21-p2.jpeg | row 3 | ROW MISSING | SC DRILL Ø17.0xFL73xOAL123-SANDVIK | (not extracted) |
| 22-p2.jpeg | row 3 | description | SC DRILL Ø13.6xFL70xOAL136-SUMITOMO | 5CDRILL13.6xFL70xOAL136-SUMITOMO |
| 22-p2.jpeg | row 4 | description | SC DRILL Ø17.0xFL73xOAL123-SANDVIK | SCDRILL017.0xFL73xOAL123-SANDVIK |
| 22-p2.jpeg | row 4 | hsnSac | 993729 | 798729 |
| 22-p2.jpeg | row 6 | srNo | 6 | - |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | row 2 | description | HOB ED10375(168619) Ø90x100-A | HOBED10375(168619)090x100-A |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | row 3 | description | HOB ED38112(PG461) Ø80x150-A | HOBED38112(PG461)080x150-A |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | row 5 | description | HOB ED31129(127138) Ø90x140-A | HOBED31129(127138)090x140-A |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | row 6 | srNo | 6 | . |
| WhatsApp Image 2026-08-01 at 01.29.17.jpeg | row 7 | srNo | 7 | None |
| WhatsApp Image 2026-08-01 at 01.29.18.jpeg | row 2 | srNo | 2 | A |
| WhatsApp Image 2026-10-08 at 00.35.20 (1).jpeg | row 6 | quantity | 1 | 11,000.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (1).jpeg | row 6 | amount | 11,000.00 | 1 |
| WhatsApp Image 2026-10-08 at 00.35.20 (10).jpeg | row 2 | srNo | 2 | 50 |
| WhatsApp Image 2026-10-08 at 00.35.20 (10).jpeg | row 2 | quantity | 1 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (10).jpeg | row 2 | amount | 3,000.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (10).jpeg | summary | igstAmount | 540.00 | 0.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (11).jpeg | row 2 | description | hob 9230 | hob9230~ 85581 10H0 |
| WhatsApp Image 2026-10-08 at 00.35.20 (11).jpeg | row 3 | description | hob 5750 | hob5750 116940 3080 |
| WhatsApp Image 2026-10-08 at 00.35.20 (12).jpeg | row 2 | srNo | 2 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (14).jpeg | row 5 | description | HOB ED38112(NP377) Ø80X150-A | HOB ED38112(NP377)080X150-A |
| WhatsApp Image 2026-10-08 at 00.35.20 (15).jpeg | row 6 | description | HOB ED23153(89909) Ø90x140-A | HOBED23153(89909)090x140-A |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | row 3 | srNo | 3 | 3 4 |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | row 4 | srNo | 4 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | row 4 | description | HOB ED24118(172834) | HOBED24118(172834) 70170 |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | row 6 | description | HOB ED24102(126915) Ø70x170 | HOBED24102(126915)070x170 |
| WhatsApp Image 2026-10-08 at 00.35.20 (17).jpeg | row 7 | description | HOB ED10406(167795) | HOBED10406(167795) 9040 |
| WhatsApp Image 2026-10-08 at 00.35.20 (18).jpeg | row 2 | ROW MISSING | CARBIDE HOB ED24122(R2961) Ø70x170 | (not extracted) |
| WhatsApp Image 2026-10-08 at 00.35.20 (19).jpeg | row 4 | basic | 9,000.00 | 9,000.00 7,000.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (19).jpeg | row 5 | basic | 7,000.00 | 1 |
| WhatsApp Image 2026-10-08 at 00.35.20 (19).jpeg | row 5 | quantity | 1 | 7,000.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (19).jpeg | row 5 | amount | 7,000.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (2).jpeg | row 6 | quantity | 1 | 12,000.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (2).jpeg | row 6 | amount | 12,000.00 | - |
| WhatsApp Image 2026-10-08 at 00.35.20 (22).jpeg | row 3 | description | HOB ED3157(176076) Ø90X170-AA | HOBED3157(176076)090X170-AA |
| WhatsApp Image 2026-10-08 at 00.35.20 (23).jpeg | row 1 | description | HOB ED846(157744) Ø100X140-A | HOBED846(157744)0100X140-A |
| WhatsApp Image 2026-10-08 at 00.35.20 (23).jpeg | row 3 | description | HOB ED38112(RG830) Ø80X150-A | HOBED38112(RG830)080X150-A |
| WhatsApp Image 2026-10-08 at 00.35.20 (24).jpeg | row 3 | description | HOB ED31121(58564) Ø90x140-A | HOBED31121(58564090x140-A |
| WhatsApp Image 2026-10-08 at 00.35.20 (25).jpeg | row 2 | srNo | 2 | 2 3 |
| WhatsApp Image 2026-10-08 at 00.35.20 (25).jpeg | row 3 | srNo | 3 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (25).jpeg | row 4 | description | SC DRILL Ø9.0xFL61xOAL103-SANDVIK | SCDRILL09.0xFL61xOAL103-SANDVIK |
| WhatsApp Image 2026-10-08 at 00.35.20 (25).jpeg | row 5 | description | SC DRILL Ø5.8xFL35xOAL75-BARGIR | SCDRILL05.8xFL35xOAL75-BARGIR |
| WhatsApp Image 2026-10-08 at 00.35.20 (26).jpeg | row 1 | description | HOB ED24126(RE717) Ø70x170 | HOB ED24126(RE717)070x170 |
| WhatsApp Image 2026-10-08 at 00.35.20 (26).jpeg | row 5 | description | HOB ED2473(126999) Ø70x170 | HOBED2473(126999)070x170 |
| WhatsApp Image 2026-10-08 at 00.35.20 (26).jpeg | row 6 | description | HOB ED2478(PG510) Ø80X160 | HOBED2478(PG510)080X160 |
| WhatsApp Image 2026-10-08 at 00.35.20 (26).jpeg | row 8 | description | GSC ED24178(169127) Ø144X28 | GSC ED24178(169127)0144X28 |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 2 | quantity | 2 | 1,200.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 2 | amount | 1,200.00 | 2 |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 4 | description | SC DRILL Ø9.1xFL22xOAL62-KCT | SC DRILL09.1xFL22xOAL62-KCT |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 6 | description | SC DRILL Ø17.0xFL73xOAL123-SANDVIK | SCDRILL017.0xFL73xOAL123-SANDVIK |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 7 | srNo | 7 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (3).jpeg | row 7 | description | STEP ENDMILL Ø13.75x15°xFL60xOAL107-FTC | STEP ENDMILL013.75x15xFL60xOAL107-FTC |
| WhatsApp Image 2026-10-08 at 00.35.20 (4).jpeg | row 2 | basic | 12,000.00 | 1 |
| WhatsApp Image 2026-10-08 at 00.35.20 (4).jpeg | row 2 | quantity | 1 | 12,000.00 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 2 | srNo | 2 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 2 | description | GSCED-5645-165699 | GSCED-5645-165699 15324 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 3 | srNo | 3 | 2 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 3 | description | GSCED-51194-166074 | GSCED-51194-166074 155925 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 3 | basic | 4,500.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 3 | quantity | 1 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 3 | amount | 4,500.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 4 | srNo | 4 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 4 | description | GSCED-7013-169433 | GSCED-7013-169433 13328 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 5 | srNo | 5 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 5 | description | GSCED-5613-24777 | GSCED-5613-24777 15035 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 6 | srNo | 6 | 5 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 6 | description | GSCED-5326-157846 | GSCED-5326-157846 146018 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 6 | quantity | 1 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 6 | amount | 4,500.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 7 | srNo | 7 | 6 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 7 | description | GSCED-1926-168588 | GSCED-1926-168588 12124 |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 7 | amount | 4,500.00 | None |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 8 | srNo | 8 | : |
| WhatsApp Image 2026-10-08 at 00.35.20 (5).jpeg | row 8 | description | GSCED-2045-23793 | GSCED-2045-23793 131922 |
| WhatsApp Image 2026-10-08 at 00.35.20 (6).jpeg | row 2 | description | CARBIDE HOB ED24127(P3578) Ø70x170 | CARBIDEHOB ED24127P3578)070x170 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 8 | ROW MISSING | GSCED-2045-18397 | (not extracted) |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 2 | description | GSCED-1067-168941 | GSCED-1067-168941 12930 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 3 | description | GSCED-5303-25820 | GSCED-5303-25820 150037 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 4 | description | GSCED-56211-20470 | GSCED-56211-20470 16019 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 5 | description | GSCED-56194-25982 | GSCED-56194-25982 164924 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 6 | description | GSCED-56254-25634 | GSCED-56254-25634 18997 |
| WhatsApp Image 2026-10-08 at 00.35.20 (8).jpeg | row 7 | description | GSCED-56254-28063 | GSCED-56254-28063 180.97 |
| WhatsApp Image 2026-10-08 at 00.35.20 (9).jpeg | row 2 | srNo | 2 | None |
| WhatsApp Image 2026-10-08 at 00.35.20.jpeg | row 2 | description | HOB ED3102(144490) Ø75x150-AA | HOB ED3102(144490)075X150-AA |
| WhatsApp Image 2026-10-08 at 00.35.20.jpeg | row 5 | description | HOB ED31113(RE724) Ø80X170-AA | HOB ED31113(RE724)080X170-AA |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 2 | description | HOB ED24103(133119) Ø70x170 | HOBED24103(133119)070x170 |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 3 | description | HOB ED2478(118670) Ø70x150 | HOBED2478118670)070x150 |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 11 | description | HOB ED53176(131940) Ø90x140 | HOBED53176131940)090x140 |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 13 | description | HOB ED2474(124625) Ø70x150 | HOBED2474(124625)070x150 |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 15 | description | HOB ED56273(44892) Ø80x140 | HOBED56273(44892)080x140 |
| WhatsApp Image 2026-10-08 at 00.35.21.jpeg | row 16 | hsnSac | 993729 | 998729 OUT-WARDUNIT-3 |