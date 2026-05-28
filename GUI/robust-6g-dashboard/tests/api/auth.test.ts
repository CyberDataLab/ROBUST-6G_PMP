import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("../../src/lib/db", () => {
  return {
    prisma: {
      user: {
        findUnique: vi.fn(),
      },
    },
  };
});

vi.mock("../../src/lib/org", () => {
  return {
    extractDomain: vi.fn((email: string) => email.split("@")[1]),
    findOrganizationByEmailDomain: vi.fn(),
  };
});

vi.mock("bcrypt", () => {
  return {
    default: {
      compare: vi.fn(),
    },
  };
});

vi.mock("jsonwebtoken", () => {
  return {
    default: {
      sign: vi.fn(() => "signed-token"),
    },
  };
});

import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import { prisma } from "../../src/lib/db";
import { findOrganizationByEmailDomain } from "../../src/lib/org";
import { POST } from "../../src/app/api/auth/login/route";

describe("Auth API", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  test("should return 400 when credentials are missing", async () => {
    const request = new Request("http://localhost/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "", password: "" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(request);
    const payload = (await response.json()) as { error?: string };

    expect(response.status).toBe(400);
    expect(payload.error).toBe("Email and password are required");
  });

  test("should return 200 and a token for valid credentials", async () => {
    vi.mocked(findOrganizationByEmailDomain).mockResolvedValue({
      id: "org-1",
      name: "ROBUST-6G",
      slug: "robust-6g",
      allowedEmailDomains: ["robust-6g.com"],
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    vi.mocked(prisma.user.findUnique).mockResolvedValue({
      id: "user-1",
      name: "Test User",
      email: "test@robust-6g.com",
      passwordHash: "hashedPassword",
      role: "ADMIN",
      organizationId: "org-1",
      createdAt: new Date(),
      updatedAt: new Date(),
    } as never);

    vi.mocked(bcrypt.compare).mockResolvedValue(true as never);
    process.env.JWT_SECRET = "test-secret";

    const request = new Request("http://localhost/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: "test@robust-6g.com",
        password: "password123",
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(request);
    const payload = (await response.json()) as { token?: string };

    expect(response.status).toBe(200);
    expect(payload.token).toBe("signed-token");
    expect(jwt.sign).toHaveBeenCalledTimes(1);
  });
});
