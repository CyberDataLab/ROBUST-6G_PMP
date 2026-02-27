import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { validateEmailDomain } from '@/policies/emailDomainAffiliation';

export async function GET(request: Request) {
    const users = await prisma.user.findMany();
    return NextResponse.json(users);
}

export async function POST(request: Request) {
    const { email, name } = await request.json();

    if (!validateEmailDomain(email)) {
        return NextResponse.json({ error: 'Invalid email domain' }, { status: 400 });
    }

    const newUser = await prisma.user.create({
        data: {
            email,
            name,
        },
    });

    return NextResponse.json(newUser, { status: 201 });
}