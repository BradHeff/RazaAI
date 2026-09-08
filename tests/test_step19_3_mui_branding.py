import tempfile
from pathlib import Path
from app.context import CuratedProjectContext

def main():
    print("="*72)
    print("RazaAI Step 19.3 MUI Branding Compatibility")
    print("="*72)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"BRANDING.md").write_text("""# Example School - Material-UI Style Guide
```javascript
const horizonColors = {
  primary: { main: '#2E5D4A', light: '#4A8B3B', dark: '#1A3429' },
  secondary: { main: '#F4B942', light: '#F6C142', dark: '#E6A832' },
  text: { primary: '#1A3429', secondary: '#495057' }
};
```
""", encoding="utf-8")
        theme=CuratedProjectContext(root).document_theme()
        assert theme["primary_color"]=="2E5D4A"
        assert theme["accent_color"]=="F4B942"
        assert theme["muted_color"]=="495057"
        assert theme["organisation"]=="Example School"
        print("[PASS] full MUI-style BRANDING.md maps into RazaAI document theme")
    print("="*72)
    print("STEP 19.3 MUI BRANDING COMPATIBILITY PASSED")
    print("="*72)

if __name__=="__main__":
    main()
