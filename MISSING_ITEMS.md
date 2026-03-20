# Outstanding Tasks & Issues

## 🔴 Critical Issues Found

### 1. **pytest Compatibility**
- Tests fail to run: `AttributeError: module 'ast' has no attribute 'Str'`
- pytest 7.3.1 incompatible with Python 3.14
- **Action needed:** Update pytest

### 2. **No .gitignore**
- output/ directory getting tracked
- logs/ directory not excluded
- venv/ not explicitly ignored
- **Action needed:** Create comprehensive .gitignore

### 3. **Stage 2 Never Tested With Real API**
- structure_case() function never called with actual Gemini API
- Token reversal logic untested
- Hallucination detection untested
- **Action needed:** Integration test with API key

### 4. **Stage 3 Excel Never Generated**
- assemble_excel() function never executed with real data
- Excel formatting untested
- Audit trail generation untested
- Token reversal untested
- **Action needed:** Full end-to-end test (mock or real API)

## ⚠️ Likely Issues (Not Verified)

### 5. **Error Handling Paths**
- Stage 2 API retries (3 attempts with backoff) - untested
- Stage 3 file not found fallback - untested
- Rate limiting (1.5s between calls) - untested
- Graceful degradation when API fails - untested

### 6. **Data Quality**
- 40% of cases fail Stage 1 validation (20/50 cases)
- Unknown if due to:
  - Document format issues
  - Classification rules too strict
  - Genuine sparse content
- Need to spot-check failing cases

### 7. **Performance**
- No timing measurements
- No API latency benchmarks
- No Excel generation profiling
- Document parsing speed unknown

### 8. **Documentation**
- No deployment guide
- No user manual
- No troubleshooting guide
- No API setup documentation
- No expected output samples

## ✅ What's Working

- ✅ Stage 1 segmenter (344 lines, tested)
- ✅ Data Minimisation (119 lines, tested)
- ✅ Stage 2 structurer (194 lines, code complete but untested)
- ✅ Stage 3 assembler (190 lines, code complete but untested)
- ✅ Safety flags (83 lines, implemented)
- ✅ Main orchestration (96 lines, imports working)
- ✅ 30/50 cases pass Stage 1 validation (60%)
- ✅ All imports fixed
- ✅ Function signatures aligned
- ✅ Integration flow complete

## Quick Fix Priority

**Must do before demo (1-2 hours):**
1. Create .gitignore (5 min)
2. Update pytest version (10 min) OR run tests via Python directly (15 min)
3. **Run full pipeline with API key** (you provide key, then test)

**Should do before hackathon (3-4 hours):**
4. Spot-check 5 failing cases to understand why
5. Create quick deployment guide
6. Document known limitations
7. Test error handling paths

**Can do later:**
8. Improve Stage 1 rules to increase pass rate
9. Performance benchmarking
10. Comprehensive documentation
