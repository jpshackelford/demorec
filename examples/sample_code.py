#!/usr/bin/env python3
"""Sample application demonstrating a REST API client."""

import requests
import json
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class User:
    """Represents a user in the system."""
    id: int
    name: str
    email: str
    active: bool = True


@dataclass  
class ApiClient:
    """Client for interacting with the REST API."""
    base_url: str
    api_key: str
    timeout: int = 30
    
    def get_users(self) -> List[User]:
        """Fetch all users from the API."""
        response = requests.get(
            f"{self.base_url}/users",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout
        )
        response.raise_for_status()
        return [User(**data) for data in response.json()]
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Fetch a single user by ID."""
        response = requests.get(
            f"{self.base_url}/users/{user_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return User(**response.json())
    
    def create_user(self, name: str, email: str) -> User:
        """Create a new user."""
        response = requests.post(
            f"{self.base_url}/users",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={"name": name, "email": email},
            timeout=self.timeout
        )
        response.raise_for_status()
        return User(**response.json())


def main():
    """Main entry point."""
    client = ApiClient(
        base_url="https://api.example.com",
        api_key="secret-key-123"
    )
    
    # Fetch and display all users
    users = client.get_users()
    for user in users:
        print(f"{user.id}: {user.name} <{user.email}>")


if __name__ == "__main__":
    main()
