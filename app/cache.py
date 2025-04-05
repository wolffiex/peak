"""
Cache module for storing and retrieving data across multiple processes.
"""

import os
import json
import functools
import psycopg2
from datetime import datetime, timedelta, timezone

# Import database constants from utils
from .utils import DATABASE_NAME, DATABASE_USER


class PostgresCache:
    """
    Postgres-based cache that works across multiple processes/workers.
    """

    def __init__(self, db_params=None):
        self.db_params = db_params or {"dbname": DATABASE_NAME, "user": DATABASE_USER}
        self._ensure_cache_table()

    def _get_connection(self):
        """Get a connection to the database"""
        return psycopg2.connect(**self.db_params)

    def _ensure_cache_table(self):
        """Ensure the cache table exists"""
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Create the cache table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """)

            # Create index on expires_at for efficient cleanup
            cur.execute("""
                CREATE INDEX IF NOT EXISTS app_cache_expires_idx ON app_cache (expires_at)
            """)

            conn.commit()
        except (Exception, psycopg2.Error) as error:
            print(f"Error creating cache table: {error}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def get(self, key):
        """Get a value from cache if it exists and is not expired"""
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Get the cache entry if it exists and is not expired
            cur.execute(
                """
                SELECT value, expires_at FROM app_cache 
                WHERE key = %s AND expires_at > NOW()
            """,
                (key,),
            )

            result = cur.fetchone()

            if result:
                # Get expiration time and calculate TTL
                expiration = result[1]
                ttl_seconds = (expiration - datetime.now(timezone.utc)).total_seconds()

                print(f"[CACHE] HIT for key: {key}")
                print(f"[CACHE] TTL remaining: {int(ttl_seconds)} seconds")

                # Deserialize the JSON value
                return json.loads(result[0])

            print(f"[CACHE] MISS for key: {key}")
            return None
        except (Exception, psycopg2.Error) as error:
            print(f"Error getting from cache: {error}")
            return None
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def set(self, key, value, ttl_seconds):
        """Set a value in the cache with expiration"""
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Serialize the value as JSON
            serialized_value = json.dumps(value)

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

            # Check if entry already exists
            cur.execute("SELECT 1 FROM app_cache WHERE key = %s", (key,))
            exists = cur.fetchone() is not None

            # Insert or update the cache entry
            cur.execute(
                """
                INSERT INTO app_cache (key, value, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) 
                DO UPDATE SET value = %s, expires_at = %s
            """,
                (key, serialized_value, expires_at, serialized_value, expires_at),
            )

            conn.commit()

            action = "UPDATED" if exists else "STORED"
            print(f"[CACHE] {action} key: {key} (expires in {ttl_seconds} seconds)")
            return True
        except (Exception, psycopg2.Error) as error:
            print(f"Error setting cache: {error}")
            if conn:
                conn.rollback()
            return False
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def cleanup_expired(self):
        """Clean up expired cache entries"""
        conn = None
        cur = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Delete expired entries
            cur.execute("DELETE FROM app_cache WHERE expires_at <= NOW()")
            deleted_count = cur.rowcount
            conn.commit()

            return deleted_count
        except (Exception, psycopg2.Error) as error:
            print(f"Error cleaning up cache: {error}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()


# Create a global cache instance
postgres_cache = PostgresCache()


def cached(ttl_seconds):
    """
    Decorator that caches function results for specified seconds.
    Works across multiple processes by using Postgres-based caching.

    This decorator works with both regular and async functions.

    Usage:
        @cached(300)  # Cache for 5 minutes
        def my_function(arg1, arg2):
            ...

        @cached(300)  # Cache for 5 minutes
        async def my_async_function(arg1, arg2):
            ...
    """
    import inspect

    def decorator(func):
        is_async = inspect.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache_key = f"{func.__module__}.{func.__name__}"
            worker_id = os.environ.get("UVICORN_WORKER_ID", "unknown")
            print(f"[CACHE] Worker {worker_id} executing {func.__name__}")

            start_time = datetime.now()
            cached_result = postgres_cache.get(cache_key)

            if cached_result is not None:
                return cached_result

            print(f"[CACHE] Worker {worker_id} executing function directly")
            result = await func(*args, **kwargs)

            try:
                postgres_cache.set(cache_key, result, ttl_seconds)
            except Exception as e:
                print(f"[CACHE] Warning: Could not cache result: {e}")

            execution_time = (datetime.now() - start_time).total_seconds()
            print(f"[CACHE] Total execution time: {execution_time:.2f} seconds")

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = f"{func.__module__}.{func.__name__}"
            worker_id = os.environ.get("UVICORN_WORKER_ID", "unknown")
            print(f"[CACHE] Worker {worker_id} executing {func.__name__}")

            start_time = datetime.now()
            cached_result = postgres_cache.get(cache_key)

            if cached_result is not None:
                return cached_result

            print(f"[CACHE] Worker {worker_id} executing function directly")
            result = func(*args, **kwargs)

            try:
                postgres_cache.set(cache_key, result, ttl_seconds)
            except Exception as e:
                print(f"[CACHE] Warning: Could not cache result: {e}")

            execution_time = (datetime.now() - start_time).total_seconds()
            print(f"[CACHE] Total execution time: {execution_time:.2f} seconds")

            return result

        return async_wrapper if is_async else sync_wrapper

    return decorator


# Add main execution to clear cache when run directly
if __name__ == "__main__":
    # When running directly, clear the cache
    print("Clearing cache...")
    deleted_count = postgres_cache.cleanup_expired()

    # Also delete all cache entries (even non-expired ones)
    conn = None
    cur = None
    try:
        conn = postgres_cache._get_connection()
        cur = conn.cursor()

        # Delete all cache entries
        cur.execute("DELETE FROM app_cache")
        all_deleted = cur.rowcount
        conn.commit()

        print(f"Deleted {deleted_count} expired cache entries")
        print(f"Deleted {all_deleted} total cache entries")
        print("Cache cleared successfully!")
    except Exception as e:
        print(f"Error clearing cache: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
