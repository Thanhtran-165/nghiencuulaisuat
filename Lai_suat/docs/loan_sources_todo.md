# Loan Sources TODO - Blocked by Technical Constraints

**Date**: 2026-01-05
**Status**: ⚠️ Only 1 source viable under no-JavaScript constraint
**Current Loan Source**: Timo (1 source)

---

## Summary

Due to the **no JavaScript engine** constraint (requests + BeautifulSoup only), most modern Vietnamese loan comparison websites cannot be scraped. This document lists the blocked loan sources and the reasons why they cannot be integrated.

**Reality**: Modern loan rate comparison sites use client-side rendering (Next.js, React, Vue) or anti-bot protection, making them incompatible with our scraping approach.

---

## Current Implementation

### ✅ Available Source (1)

#### 1. Timo - Loan Rates

**URL**: `https://timo.vn/blogs/lai-suat-vay-tin-chap-ngan-hang-nao-cao-nhat/`

**Status**: ✅ **IN PRODUCTION** - Only viable source under no-JS constraint

**Coverage**:
- Secured loans (thế chấp): Mortgage rates
- Unsecured loans (tín chấp): Personal loan rates
- Min/Max rate ranges per bank

**Priority**: 1 (highest priority for merge)

---

## Blocked Sources (Cannot be Integrated)

### ❌ 1. Cake.vn

**URL**: `https://cake.vn/tin-tuc/tai-chinh/lai-suat-vay-ngan-hang`

**Reason**: **Next.js Client-Side Rendering**

**Evidence**:
```html
<!--$!-->
<template data-dgst="BAILOUT_TO_CLIENT_SIDE_RENDERING"></template>
<!--/$-->
```

The page is a React/Next.js application that renders all content on the client side. The initial HTML response contains only loading templates and requires JavaScript execution to display loan rate data.

**Block Type**: JavaScript-rendered

**Workaround Options**:
- Use Selenium/Playwright (❌ violates no-JS constraint)
- Find their API endpoints (if any public API exists)

**Recommendation**: ❌ **EXCLUDE** - Requires browser execution

---

### ❌ 2. Topi.vn

**URL**: `https://topi.vn/so-sanh-lai-suat-vay-ngan-hang.html`

**Reason**: **JavaScript-Loaded Content**

**Evidence**: When fetching with `requests` + `BeautifulSoup`:
- No table structure found in HTML response
- Empty container divs that are populated by JavaScript
- Likely uses AJAX to fetch data after page load

**Block Type**: JavaScript-rendered

**Workaround Options**:
- Reverse-engineer AJAX endpoints (may require authentication/API keys)
- Use browser automation (❌ violates no-JS constraint)

**Recommendation**: ❌ **EXCLUDE** - Requires browser or API access

---

### ❌ 3. Cafef.vn

**URL**: `https://cafef.vn/du-lieu/lai-suat-ngan-hang.chn`

**Reason**: **JavaScript Rendering with Template Literals**

**Evidence**:
```html
<script>
table_item += `<tr>
  <td><img src="${item.icon}" /><span>${item.name}</span></td>
  <td>${this.renderText(item.interestRates[i].value)}</td>
```

Loan rate data is rendered using JavaScript template literals. The HTML contains only template code, not actual rate values.

**Block Type**: JavaScript-rendered

**Workaround Options**:
- Execute JavaScript (❌ violates no-JS constraint)
- Find their data API (undocumented, may require reverse-engineering)

**Recommendation**: ❌ **EXCLUDE** - Requires JavaScript execution

---

### ❌ 4. Webgia.com

**URL**: `https://webgia.com/lai-suat/vay-tin-chap/` (and other loan pages)

**Reason**: **Base64 Obfuscation + Anti-Bot**

**Evidence**:
```html
<td class="text-right lsd" nb="3HSZ0E2c313PS0WY">
  <small>webgiá.com</small>
</td>
```

Loan rate values are **obfuscated with base64 encoding** in HTML attributes (`nb="..."`). To extract rates, you would need to:
1. Extract base64 strings from attributes
2. Decode each base64 string
3. Parse decoded values
4. Handle encoding variations

**Block Type**: Anti-bot / Obfuscation

**Workaround Options**:
- Implement base64 decoder (possible but fragile - encoding may change)
- Browser automation (❌ violates no-JS constraint)

**Recommendation**: ❌ **EXCLUDE** - Too complex, encoding scheme may change

---

### ❌ 5. Bank Official Websites

#### a. Vietcombank

**URL**: `https://www.vietcombank.com/iib-v2/Lai-suat-vay`

**Reason**: **Anti-Bot Protection**

**Evidence**: Redirects to `/lander` or returns CAPTCHA when accessed with `requests`

**Block Type**: Anti-bot

**Recommendation**: ❌ **EXCLUDE** - Actively blocks scrapers

---

#### b. VPBank

**URL**: `https://www.vpbank.com.vn/lai-suat-vay-dung-tin-chap/`

**Reason**: **React SPA**

**Evidence**: Returns minimal HTML skeleton, all content rendered by client-side React

**Block Type**: JavaScript-rendered

**Recommendation**: ❌ **EXCLUDE** - Requires browser

---

#### c. Other Major Banks (Techcombank, MB, BIDV, etc.)

**Reason**: **Modern Web Architecture**

Most major Vietnamese banks have migrated to:
- Single Page Applications (SPA)
- Client-side rendering
- Anti-bot protection (Cloudflare, Akamai)
- Authentication-gated rate information

**Block Type**: JavaScript-rendered + Anti-bot

**Recommendation**: ❌ **EXCLUDE** - Not feasible without browser

---

## Why Only Timo?

### Technical Constraints

Our scraper architecture uses:
- **requests** - HTTP library only
- **BeautifulSoup** - HTML parsing only
- **NO Selenium/Playwright** - No JavaScript engine

This works for:
- ✅ Static HTML tables (old web architecture)
- ✅ Server-side rendered content

This fails for:
- ❌ Client-side rendering (React/Next.js/Vue)
- ❌ JavaScript-generated content
- ❌ Anti-bot protection (Cloudflare, CAPTCHA)
- ❌ Obfuscated data (base64, encryption)

### The Landscape

**Deposit Rates**: Better availability (2 sources: Timo + 24hmoney)
- Older comparison sites still use static HTML tables
- Less competitive → less anti-bot protection

**Loan Rates**: Scarce availability (1 source: Timo only)
- Newer comparison sites use modern JS frameworks
- More competitive → more anti-bot measures
- Bank official sites heavily protected

---

## Potential Workarounds (Future Considerations)

### Option 1: Relax No-JS Constraint (Not Recommended)

Add **optional** Playwright support for JS sites:
```python
# Pseudo-code
if url in JS_SOURCES:
    return scrape_with_playwright(url)  # Optional dependency
else:
    return scrape_with_requests(url)   # Default behavior
```

**Pros**:
- Could add 3-5 more loan sources
- More comprehensive coverage

**Cons**:
- Adds complexity (need to install Chromium/Playwright)
- Heavier resource usage
- Breaks "simple scraping" philosophy

**Recommendation**: Only consider if business requirements demand more loan sources

---

### Option 2: API Endpoints

Some sites may have undocumented JSON APIs:
```bash
# Example: Find AJAX endpoints
curl -s "https://example.com/api/loan-rates" | jq
```

**Challenges**:
- APIs are undocumented
- May require authentication/tokens
- May have CORS restrictions
- Could change without notice

**Recommendation**: ⚠️ **EXPERIMENTAL** - Could try reverse-engineering, but fragile

---

### Option 3: PDF Rate Sheets

Some banks publish loan rates as PDF files:
- Download PDF (static file)
- Parse PDF with `pdfplumber` or `PyPDF2`
- Extract rate tables

**Challenges**:
- PDF parsing is error-prone
- Format varies by bank
- Not all banks publish PDFs
- OCR may be needed for scanned PDFs

**Recommendation**: ⚠️ **MAYBE** - Could work for some banks, but labor-intensive

---

### Option 4: Government/NHV Source

Check State Bank of Vietnam (Ngân House Nhà Nước):
- Reference rates (lãi suất tái cấp vốn)
- May have public data feeds

**Status**: Not yet researched

**Recommendation**: ⚠️ **RESEARCH** - Could provide reference rates if available

---

## Current Strategy

### Accept Limitations

Given the technical constraints, we accept that:
- **Deposit rates**: 2 sources (Timo + 24hmoney) ✅ Good coverage
- **Loan rates**: 1 source (Timo only) ⚠️ Limited but functional

### Mitigate User Impact

1. **Transparency**: UI note "Nguồn lãi suất vay hiện có: Timo (1 nguồn)"
2. **Quality**: Ensure Timo loan data is accurate and up-to-date
3. **Priority**: Set Timo as priority=1 in source merge system
4. **Future-Proofing**: Document blocked sources for future reference

---

## Next Steps

### Immediate (Accept Constraint)

1. ✅ **Document this limitation** in `docs/loan_sources_todo.md` (you are here)
2. ✅ **Add UI note** to inform users (completed in task E)
3. ⏳ **Monitor industry**: Watch for new static HTML sources

### Long-Term (If Needed)

1. **Research PDF sources**: Check if banks publish loan rate PDFs
2. **Explore APIs**: Look for public loan rate APIs
3. **Consider Playwright**: If business requirements demand more sources
4. **NHV reference rates**: Check State Bank of Vietnam for reference rates

---

## Conclusion

**Only 1 loan source (Timo) is viable** under our current no-JavaScript constraint. This is a technical limitation imposed by modern web architecture, not a failure of the scraper.

The scraper works correctly - it's just that the modern web has moved away from static HTML.

**Recommendation**: Accept the limitation and focus on:
- ✅ Quality > Quantity (1 good source is better than 5 broken ones)
- ✅ Transparency (inform users about limited sources)
- ✅ Future-proofing (keep documentation for potential future work)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-05
**Maintainer**: Claude Code (Agent)
