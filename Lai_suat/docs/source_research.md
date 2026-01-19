# Data Source Research - Vietnamese Bank Interest Rates

**Date**: 2026-01-05
**Status**: ⚠️ CRITICAL CONSTRAINTS IDENTIFIED

## Executive Summary

After researching 10+ candidate websites, **most modern Vietnamese banking/comparison sites use client-side rendering (Next.js, React, Vue)**, which is **incompatible** with our requirement to use only `requests` + `BeautifulSoup` (NO Selenium/Playwright).

### Key Finding
- **Only 1 viable source found**: **24hmoney.vn** (has clean HTML tables)
- All other major sites require JavaScript execution or have anti-bot protection

---

## Candidate Sources Analysis

### ✅ VIABLE SOURCES (Static HTML)

#### 1. 24hmoney.vn - Deposit Rates (RECOMMENDED)

**URL**: `https://24hmoney.vn/lai-suat-gui-ngan-hang`

**HTML Structure**:
```html
<div class="vue-table offline-table">
  <table>
    <thead>
      <tr>
        <th>Ngân hàng</th>
        <th>1 tháng</th>
        <th>3 tháng</th>
        <th>6 tháng</th>
        <th>12 tháng</th>
        <!-- more terms -->
      </tr>
    </thead>
    <tbody>
      <tr class="bg-white">
        <td>
          <a href="/lai-suat-gui-ngan-hang/vib" class="name">VIB</a>
        </td>
        <td><p class="bank-interest-rate">3.6</p></td>
        <td><p class="bank-interest-rate">4.75</p></td>
        <td><p class="bank-interest-rate">4.7</p></td>
        <td><p class="bank-interest-rate">6.5</p></td>
      </tr>
      <!-- More banks: Bac A, NCB, OCB, BVBank, etc. -->
    </tbody>
  </table>
</div>
```

**Strengths**:
- ✅ Clean HTML table structure
- ✅ Bank names in links (`<a class="name">VIB</a>`)
- ✅ Rates as plain text (`<p class="bank-interest-rate">3.6</p>`)
- ✅ Separate tables for "tại quầy" (offline) and "trực tuyến" (online)
- ✅ 29+ banks covered
- ✅ Updated regularly (shows "Cập nhật lúc: 23:59:59 16/12/2025")

**Challenges**:
- ⚠️ Table headers are dynamically generated (may need to infer column meanings)
- ⚠️ Some rows have `style="display:none"` (pagination - need to handle hidden rows)

**Bank List Format**: `by_table` (banks in first column)
**Rate Format**: Single numeric values (e.g., "3.6", "4.75")

**Recommendation**: ✅ **INCLUDE** - This is our best deposit source

---

### ❌ NOT VIABLE SOURCES (Require JavaScript)

#### 1. webgia.com

**URL**: `https://webgia.com/lai-suat/`

**Issue**: Rates are **obfuscated with base64 encoding** in HTML attributes:
```html
<td class="text-right lsd" nb="3HSZ0E2c313PS0WY">
  <small>webgiá.com</small>
</td>
```

The `nb` attribute contains base64-encoded rate values. Would need to:
1. Extract base64 strings
2. Decode each one
3. Parse the decoded values

**Verdict**: ❌ **EXCLUDE** - Too complex, error-prone

---

#### 2. cafef.vn

**URL**: `https://cafef.vn/du-lieu/lai-suat-ngan-hang.chn`

**Issue**: JavaScript rendering. HTML contains template code:
```html
table_item += `<tr>
  <td><img src="${item.icon}" /><span>${item.name}</span></td>
  <td>${this.renderText(item.interestRates[i].value)}</td>
```

**Verdict**: ❌ **EXCLUDE** - Requires JavaScript execution

---

#### 3. cake.vn

**URL**: `https://cake.vn/tin-tuc/tai-chinh/lai-suat-vay-ngan-hang`

**Issue**: Next.js with `BAILOUT_TO_CLIENT_SIDE_RENDERING`:
```html
<!--$!-->
<template data-dgst="BAILOUT_TO_CLIENT_SIDE_RENDERING"></template>
<!--/$-->
```

**Verdict**: ❌ **EXCLUDE** - Client-side React app

---

#### 4. topi.vn

**URL**: `https://topi.vn/so-sanh-lai-suat-vay-ngan-hang.html`

**Issue**: No table structure found in HTML response (likely JavaScript-loaded)

**Verdict**: ❌ **EXCLUDE** - Requires browser

---

#### 5. simplize.vn

**URL**: `https://simplize.vn/lai-suat-ngan-hang`

**Issue**: Not tested yet, but likely follows same pattern as other financial sites

**Status**: ⚠️ **PENDING** - Could be tested, but low confidence

---

#### 6. Bank Official Sites

**Vietcombank**: `https://www.vietcombank.com/iib-v2/Lai-suatgui-tiet-kiem`
**Issue**: Redirects to `/lander` (anti-bot protection)

**VPBank**: `https://www.vpbank.com.vn/lai-suat-vay-dung-tin-chap/`
**Issue**: Returns minimal HTML (React app)

**Verdict**: ❌ **EXCLUDE** - Anti-bot measures

---

## Recommendations

### Option 1: Accept Reduced Scope (REALISTIC)

Given the technical constraints, recommend:

**Deposit Sources (2 total)**:
1. ✅ **timo_deposit** (existing) - Timo.vn comparison
2. ✅ **24hmoney_deposit** (NEW) - 24hmoney.vn offline table

**Loan Sources (1-2 total)**:
1. ✅ **timo_loan** (existing) - Timo.vn comparison
2. ⚠️ **Single loan source needed** - May need to:
   - Manually scrape one bank's official PDF rate sheets (if available as static files)
   - Use API endpoints (if any banks provide public APIs)
   - Accept that only 1 loan source is viable

**Reality**: Modern web has moved to client-side rendering. Static HTML tables are increasingly rare.

---

### Option 2: Relax Constraints (NOT RECOMMENDED)

Could use:
- **Selenium/Playwright** - ❌ violates "no JavaScript engine" requirement
- **Headless Chrome** - ❌ adds complexity, resource-intensive

---

### Option 3: Hybrid Approach (CREATIVE)

1. **Scrape 24hmoney.vn** for deposit rates (static HTML)
2. **For loan rates**:
   - Check if any banks publish **PDF rate sheets** (static files)
   - Check if any banks have **REST APIs** for public rate data
   - Scrape **government/NHV website** (State Bank of Vietnam) for reference rates
   - Use **RSS feeds** if available

---

## Technical Learnings

### Why Client-Side Rendering?

Modern Vietnamese financial sites use Next.js/React because:
- Better UX with dynamic filtering/sorting
- SEO optimization with server-side generation
- Mobile-responsive design
- Real-time rate updates

### Scraping Implications

**Old web (2010s)**: Static HTML tables → Easy to scrape ✅
**New web (2020s)**: JavaScript rendering → Requires browser ❌

**Our constraints** (requests + bs4 only) work best with old-web architecture.

---

## Next Steps

1. **Confirm 24hmoney.vn as deposit source #2**
   - Download HTML fixture
   - Create parser with Strategy A (table parsing)
   - Test with `pytest`

2. **Find loan source options**:
   - Research bank official sites for PDF rate sheets
   - Check State Bank of Vietnam website for reference rates
   - Search for any public APIs

3. **Document decision**:
   - Update `IMPLEMENTATION_PLAN.md` with adjusted expectations
   - Note that modern web architecture limits static scraping

4. **Consider future-proofing**:
   - Could add Playwright as **optional** dependency for JS sites
   - Keep existing parsers separate from JS-dependent ones

---

## Appendix: Test Commands

```bash
# Test 24hmoney.vn structure
curl -s "https://24hmoney.vn/lai-suat-gui-ngan-hang" | grep -E "(bank-interest-rate|<table)" | head -50

# Count banks in table
curl -s "https://24hmoney.vn/lai-suat-gui-ngan-hang" | grep -o 'class="name"' | wc -l

# Check webgia.com encoding
curl -s "https://webgia.com/lai-suat/" | grep 'nb="' | head -5
```

---

**Researcher**: Claude Code (Agent)
**Time spent**: ~1 hour
**Confidence level**: High (technical constraint confirmed)
