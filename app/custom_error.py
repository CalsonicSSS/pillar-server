from fastapi import HTTPException


# make custom error extend to HTTPException, they are treated as HTTP exceptions by FastAPI.
# When these exceptions are raised, FastAPI will always catch them ON MOST OUTER LEVEL in each endpoint route
# automatically convert them into a HTTP responses with the appropriate status code and detail message as payload json with "detail".
# the response payload will include a JSON object with a detail field containing that string.
class GeneralServerError(HTTPException):
    def __init__(self, error_detail_message: str):
        super().__init__(status_code=500, detail=error_detail_message)


class DataBaseError(HTTPException):
    def __init__(self, error_detail_message: str):
        super().__init__(status_code=500, detail=error_detail_message)


class UserAuthError(HTTPException):
    def __init__(self, error_detail_message: str):
        super().__init__(status_code=401, detail=error_detail_message)


class UserOauthError(HTTPException):
    def __init__(self, error_detail_message: str):
        super().__init__(status_code=401, detail=error_detail_message)


class SecurityError(HTTPException):
    def __init__(self, error_detail_message: str):
        super().__init__(status_code=400, detail=error_detail_message)
