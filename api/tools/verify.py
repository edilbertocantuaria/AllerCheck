import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "api" / "tools"
ENV_FILE = PROJECT_ROOT / ".env"

REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "REWRITE_TEMPERATURE",
    "ANSWER_TEMPERATURE",
    "EVALUATOR_TEMPERATURE",
]

EXPECTED_INPUT_FILES = [
    TOOLS_ROOT / "data" / "raw" / "asbai" / "ALERGIA-PERGUNTAS-E-RESPOSTAS.pdf",
    TOOLS_ROOT / "data" / "raw" / "vigimed" / "VigiMed_Reacoes.csv",
    TOOLS_ROOT / "data" / "raw" / "vigimed" / "VigiMed_Medicamentos.csv",
    TOOLS_ROOT / "data" / "raw" / "vigimed" / "VigiMed_Notificacoes.csv",
]

OUTPUT_DIRS = [
    TOOLS_ROOT / "data" / "processed" / "asbai",
    TOOLS_ROOT / "data" / "processed" / "vigimed",
    TOOLS_ROOT / "data" / "processed" / "allergia_meds",
    TOOLS_ROOT / "data" / "processed" / "evaluation",
]


def check_env_file() -> bool:
    if not ENV_FILE.exists():
        print(f"❌ .env file not found at {ENV_FILE}")
        print(f"   → Copy from .env.example: cp .env.example .env")
        return False

    print(f"✅ .env file found at {ENV_FILE}")
    return True


def check_env_vars() -> bool:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)

    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        print(f"❌ Missing environment variables:")
        for var in missing:
            print(f"   → {var}")
        return False

    print(f"✅ All required env vars defined: {', '.join(REQUIRED_ENV_VARS)}")
    return True


def check_input_files() -> bool:
    print("\n📁 Input Files:")
    all_exist = True

    for file_path in EXPECTED_INPUT_FILES:
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"   ✅ {file_path.name} ({size_mb:.1f} MB)")
        else:
            print(f"   ⚠️  {file_path.name} not found")
            all_exist = False

    if not all_exist:
        print("\n   → Some input files missing. Download from:")
        print("      ASBAI: https://www.asbai.org.br")
        print("      VigiMed: https://www.gov.br/anvisa/pt-br/assuntos/farmacovigilancia")
        return False

    return True


def check_output_dirs() -> bool:
    print("\n📂 Output Directories:")
    all_writable = True

    for dir_path in OUTPUT_DIRS:
        dir_path.mkdir(parents=True, exist_ok=True)

        test_file = dir_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            print(f"   ✅ {dir_path.name}")
        except Exception as e:
            print(f"   ❌ {dir_path.name} — {e}")
            all_writable = False

    return all_writable


def check_imports() -> bool:
    print("\n🐍 Python Imports:")

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "api"))

        from tools.pipelines.common.io import save_with_timestamp, load_file
        from tools.pipelines.common.logger import setup_logger

        print("   ✅ tools.pipelines.common")

        from tools.evaluation.ragas.helpers import ALL_METRICS

        print("   ✅ tools.evaluation.ragas.helpers")

        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False


def main() -> int:
    print("=" * 70)
    print("  🛠️  Tools Configuration Verification")
    print("=" * 70 + "\n")

    checks = [
        ("Environment File", check_env_file),
        ("Environment Variables", check_env_vars),
        ("Input Files", check_input_files),
        ("Output Directories", check_output_dirs),
        ("Python Imports", check_imports),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n🔍 {name}:")
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append(False)

    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"✅ All checks passed ({passed}/{total})")
        print("\n   Ready to run pipelines!")
        print("   → python -m tools.pipelines.vigimed.run")
        return 0
    else:
        print(f"❌ Some checks failed ({passed}/{total})")
        print("\n   Fix issues above and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
