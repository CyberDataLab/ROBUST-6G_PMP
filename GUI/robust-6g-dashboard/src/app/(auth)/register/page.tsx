"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type RegisterFormState = {
  email: string;
  password: string;
  role: "USER" | "ADMIN";
};

/** """Renders the registration page and submits user data to the registration API.""" */
const RegisterPage = () => {
  const [form, setForm] = useState<RegisterFormState>({
    email: "",
    password: "",
    role: "USER",
  });
  const [error, setError] = useState("");
  const router = useRouter();

  /** """Updates a specific form field while preserving the rest of the form state.""" */
  const updateField = <K extends keyof RegisterFormState>(
    key: K,
    value: RegisterFormState[K],
  ) => {
    setForm((previousForm) => ({
      ...previousForm,
      [key]: value,
    }));
  };

  /** """Submits registration data and redirects the user when registration is successful.""" */
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(form),
    });

    if (!response.ok) {
      const payload = (await response.json()) as { error?: string };
      setError(payload.error ?? "Registration failed. Please try again.");
      return;
    }

    router.push("/login");
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center">
      <h1 className="mb-4 text-2xl font-bold">Register</h1>
      {error ? <p className="text-red-500">{error}</p> : null}
      <form onSubmit={handleSubmit} className="w-full max-w-sm">
        <div className="mb-4">
          <label className="block text-gray-700" htmlFor="email">
            Email
          </label>
          <input
            type="email"
            id="email"
            value={form.email}
            onChange={(event) => updateField("email", event.target.value)}
            required
            className="mt-1 block w-full rounded-md border border-gray-300 p-2"
          />
        </div>
        <div className="mb-4">
          <label className="block text-gray-700" htmlFor="password">
            Password
          </label>
          <input
            type="password"
            id="password"
            value={form.password}
            onChange={(event) => updateField("password", event.target.value)}
            required
            className="mt-1 block w-full rounded-md border border-gray-300 p-2"
          />
        </div>
        <div className="mb-6">
          <label className="block text-gray-700" htmlFor="role">
            Role
          </label>
          <select
            id="role"
            value={form.role}
            onChange={(event) =>
              updateField("role", event.target.value as "USER" | "ADMIN")
            }
            className="mt-1 block w-full rounded-md border border-gray-300 p-2"
          >
            <option value="USER">User</option>
            <option value="ADMIN">Admin</option>
          </select>
        </div>
        <button
          type="submit"
          className="w-full rounded bg-blue-500 py-2 font-bold text-white"
        >
          Register
        </button>
      </form>
    </div>
  );
};

export default RegisterPage;
