import sys
try:
    from main import app
    print("Successfully imported app")
except Exception as e:
    import traceback
    traceback.print_exc()
