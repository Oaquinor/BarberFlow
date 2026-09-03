# Contributing to KingFlow Barber

Thank you for your interest in contributing to KingFlow Barber!

---

## 📋 Before You Start

1. Read [STANDARDS.md](docs/STANDARDS.md)
2. Read [ARCHITECTURE.md](docs/ARCHITECTURE.md)
3. Understand the project structure
4. Set up development environment

---

## 🔀 Development Workflow

### 1. Fork & Clone

```bash
git clone https://github.com/your-username/kingflow-barber.git
cd kingflow-barber
```

### 2. Create Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

**Branch naming:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation
- `refactor/` - Code refactoring
- `test/` - Adding tests

### 3. Make Changes

Follow our coding standards:
- ✅ Use type hints
- ✅ Write docstrings
- ✅ Follow naming conventions (snake_case for functions/variables, PascalCase for classes)
- ✅ Keep functions small and focused
- ✅ Write tests
- ✅ Update documentation

### 4. Test Your Changes

```bash
# Run tests
pytest

# Check code formatting
black app/ --check
isort app/ --check

# Type checking
mypy app/
```

### 5. Commit

```bash
git add .
git commit -m "feat: add barber availability check"
```

**Commit message format:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting)
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

### 6. Push & Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

---

## ✅ Pull Request Checklist

Before submitting:

- [ ] Code follows project standards
- [ ] All tests pass
- [ ] New tests added (if applicable)
- [ ] Documentation updated (if applicable)
- [ ] No merge conflicts
- [ ] Clear commit messages
- [ ] PR description explains changes

---

## 🧪 Writing Tests

### Test Structure

```python
"""
Module description.

Tests for [functionality].
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_feature_name(client: AsyncClient):
    """Test specific functionality."""
    # Arrange
    data = {"key": "value"}

    # Act
    response = await client.post("/endpoint", json=data)

    # Assert
    assert response.status_code == 200
    assert response.json()["success"] is True
```

### Test Naming

- Use descriptive names: `test_create_appointment_with_valid_data`
- Follow pattern: `test_[action]_[condition]_[expected_result]`

---

## 📝 Documentation

### Code Comments

Only comment complex logic or important business rules:

```python
# Calculate commission based on tier (10% basic, 15% silver, 20% gold)
commission = amount * COMMISSION_RATES[affiliate.tier]
```

### Docstrings

All public functions need docstrings:

```python
def calculate_commission(amount: float, rate: float) -> float:
    """
    Calculate commission based on amount and rate.

    Args:
        amount: Total sale amount
        rate: Commission rate (0.0 to 1.0)

    Returns:
        Calculated commission amount

    Raises:
        ValueError: If rate is invalid
    """
    if not 0 <= rate <= 1:
        raise ValueError("Rate must be between 0 and 1")
    return amount * rate
```

---

## 🚫 What NOT to Do

- ❌ Don't push directly to `main` branch
- ❌ Don't commit `.env` files or secrets
- ❌ Don't write code without tests
- ❌ Don't ignore linting errors
- ❌ Don't use `print()` for debugging (use logger)
- ❌ Don't add unnecessary dependencies
- ❌ Don't write overly complex code

---

## 🎯 Code Review Process

1. **Automated checks** run on PR
2. **Code review** by maintainers
3. **Changes requested** (if needed)
4. **Approval** from at least 1 maintainer
5. **Merge** to main branch

---

## 💡 Feature Requests

Have an idea? We'd love to hear it!

1. Check existing issues
2. Create new issue with:
   - Clear description
   - Use case
   - Expected behavior
   - Mockups (if UI change)

---

## 🐛 Bug Reports

Found a bug?

1. Check if already reported
2. Create issue with:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Screenshots
   - Environment details

---

## 📞 Questions?

- **GitHub Issues**: For bugs and features
- **GitHub Discussions**: For questions and ideas
- **Email**: dev@noventiagroup.com

---

## 📜 Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Give constructive feedback
- Focus on the code, not the person
- Help others learn

---

## 🏆 Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Part of the KingFlow Barber community

---

Thank you for contributing! 🎉

**© 2024 NOVENTIA GROUP**
