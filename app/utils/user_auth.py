import jwt
from jwt.jwks_client import PyJWKClient
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID
import traceback
from app.core.config import app_config_settings
from app.services.user_services import get_user_by_clerk_id
from app.custom_error import UserAuthError
from app.utils.app_states import get_async_supabase_client
from supabase._async.client import AsyncClient


# Clerk automatically generates a new JSON Web Token (JWT) for each user upon sign-up or subsequent login each time ON DEMAND (clerk handles everything)
# This token is signed with Clerk's private key, and it contains information about the user, such as their ID and any custom claims you may have added.
# jwt is mainly used for user authentication and authorization purposes without the need to store session data on the server and no need to query the database for user information on every request.
# jwt itself alone already contains all the information needed to identify the user (very important)

# after user signup / login:
# User go through Clerk via email/password or Google OAuth or other methods
# Clerk issues a JWT based on a chosen template (with signature signed default by clerk private key)
# if its first time signing up, Clerk will create a new user and then fastapi will create corresponding user in Supabase through webhook.

# user auth flow:
# 1	Client sends HTTP request with header: Authorization: Bearer <jwt_token>
# 2	FastAPI sees Depends(security), runs security()
# 3	security() extracts token and wraps it inside HTTPAuthorizationCredentials class, and then it can used to retrieves jwt from it.
# 4	we then calls jwt.decode to verify and decode the JWT using Clerk's public keys
# 5	If OK, returns the decoded payload portion in dictionary + extracts the Clerk ID from the token
# 6	uses get_user_by_clerk_id to find the corresponding Supabase user and retrieve the final supabase user_id


# HTTPBearer is a class from fastapi.security that expects the client side to send a token in the HTTP "Authorization: Bearer <token>" header.
# this creates an instance of the HTTPBearer class, but this instance is also callable
# So while security is an instance of HTTPBearer, it also behaves like a function, to do something like security(request)
# it will do: 1. Read the incoming HTTP request. 2. Look for Authorization: Bearer <token>. 3. If has, it will extract the token and return it as an HTTPAuthorizationCredentials object.
security = HTTPBearer()

# Initialize the JWKS client
# This URL points to Clerk's public JSON Web Key Set (JWKS) — it contains the public keys that correspond to the private key Clerk uses to sign JWTs.
# we use this fetched public key to verify the JWT signature.
jwks_url = f"https://{app_config_settings.CLERK_DOMAIN}/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url)


# Depends(security): Tell FastAPI to run security() first before calling get_current_user.
# HTTPAuthorizationCredentials: It's a small data class as pydantic model with two fields: "scheme" and "credentials".
# scheme: the type of authentication (in this case, it will be "Bearer") | credentials: the actual token sent by the client.
async def verify_jwt_and_get_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security), supabase: AsyncClient = Depends(get_async_supabase_client)
) -> UUID:
    print("verify_jwt_and_get_user_id function runs")
    try:
        # Extract the JWT token from the credentials
        jwt_token = credentials.credentials

        # Get the signing key
        signing_key = jwks_client.get_signing_key_from_jwt(jwt_token)

        # When using Clerk, will need to verify the JWT using Clerk's signing_key. Which is actually the key you get from the JWKS endpoint through JWKS URL
        # what jwt.decode does:
        # 1: unpacks the three parts of JWT: header, payload, signature.
        # 2. It verifies if the signature (Recomputes the signature from the header + payload part, and compares it with the signature part).
        # 3. If matches, it gives you the "payload" portion back as a Python dictionary.
        # 4. If not matches, it raises an exception.
        jwt_payload = jwt.decode(
            jwt_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=app_config_settings.CLERK_JWT_AUDIENCE,
            issuer=f"https://{app_config_settings.CLERK_DOMAIN}",
        )

        # Get user ID from the token - try both "sub" and "user_id"
        clerk_id = jwt_payload.get("sub")
        if not clerk_id:
            raise UserAuthError(error_detail_message="Invalid token: no user identifier found")

        # Look up the user in Supabase by Clerk ID
        user = await get_user_by_clerk_id(supabase, clerk_id)

        return user.id  # this will be uuid data type

    except Exception as e:
        print(traceback.format_exc())
        print(str(e))
        raise UserAuthError(error_detail_message="User not authenticated successfully")
