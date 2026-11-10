class AppError(Exception):
    def __init__(self, code, message, status=400, diagnostics=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.diagnostics = diagnostics or {}
