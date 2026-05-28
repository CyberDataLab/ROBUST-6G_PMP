import { NextResponse } from "next/server";
import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import { prisma } from "@/lib/db";
import { extractDomain, findOrganizationByEmailDomain } from "@/lib/org";

/** """Authenticates a user with email and password and returns a signed JWT.""" */
export async function POST(request: Request) {
  const body = (await request.json()) as {
    email?: string;
    password?: string;
  };

  const email = String(body.email ?? "").trim().toLowerCase();
  const password = String(body.password ?? "");

  if (!email || !password) {
    return NextResponse.json(
      { error: "Email and password are required" },
      { status: 400 },
    );
  }

  let domain = "";
  try {
    domain = extractDomain(email);
  } catch {
    return NextResponse.json({ error: "Invalid email format" }, { status: 400 });
  }

  const organization = await findOrganizationByEmailDomain(domain);
  if (!organization) {
    return NextResponse.json({ error: "Email domain is not allowed" }, { status: 403 });
  }

  const user = await prisma.user.findUnique({
    where: { email },
  });

  if (!user) {
    return NextResponse.json({ error: "Invalid email or password" }, { status: 401 });
  }

  const isPasswordValid = await bcrypt.compare(password, user.passwordHash);
  if (!isPasswordValid) {
    return NextResponse.json({ error: "Invalid email or password" }, { status: 401 });
  }

  const jwtSecret = process.env.JWT_SECRET;
  if (!jwtSecret) {
    return NextResponse.json({ error: "JWT secret is not configured" }, { status: 500 });
  }

  const token = jwt.sign({ userId: user.id, role: user.role }, jwtSecret, {
    expiresIn: "1h",
  });

  return NextResponse.json({ token });
}
