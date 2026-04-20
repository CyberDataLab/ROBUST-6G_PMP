import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { validateEmailDomain } from '@/policies/emailDomainAffiliation';

export async function POST(request: Request) {
    const { email, password } = await request.json();

    // Validate email domain
    if (!validateEmailDomain(email)) {
        return NextResponse.json({ error: 'Invalid email domain' }, { status: 400 });
    }

    // Check if user already exists
    const existingUser = await prisma.user.findUnique({
        where: { email },
    });

    if (existingUser) {
        return NextResponse.json({ error: 'User already exists' }, { status: 409 });
    }

    // Create new user
    const newUser = await prisma.user.create({
        data: {
            email,
            password, // In a real application, ensure to hash the password
        },
    });

    return NextResponse.json({ user: newUser }, { status: 201 });
}