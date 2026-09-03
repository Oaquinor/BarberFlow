"""
Initialize default achievements in the database.

Run this script once to populate the achievements table.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services import AchievementService


def main():
    """Initialize default achievements."""
    print("🎮 Initializing default achievements...")

    db = SessionLocal()

    try:
        AchievementService.initialize_default_achievements(db)
        print("✅ Default achievements created successfully!")
        print("\nAchievements added:")
        print("  🎉 Primer Día")
        print("  🔥 Guerrero Semanal")
        print("  👑 Maestro del Mes")
        print("  🐝 Abeja Ocupada")
        print("  ⚡ Super Barbero")
        print("  💯 Club de los 100")
        print("  🌟 Quinientos")
        print("  🏆 Leyenda")
        print("  ⚡ Demonio de la Velocidad")
        print("  ✨ Semana Perfecta")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
