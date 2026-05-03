from src.config import settings
print(f"TARGET_CASH_PER_LEG exists: {hasattr(settings, 'TARGET_CASH_PER_LEG')}")
if hasattr(settings, 'TARGET_CASH_PER_LEG'):
    print(f"Value: {settings.TARGET_CASH_PER_LEG}")
else:
    print("Attributes in settings:")
    print(dir(settings))
