import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { validateEmailDomain } from '@/policies/emailDomainAffiliation';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

export async function POST(request: Request) {
    const { email, password } = await request.json();

    if (!email || !password) {
        return NextResponse.json({ error: 'Email and password are required' }, { status: 400 });
    }

    const isValidDomain = validateEmailDomain(email, 'robust-6g');
    if (!isValidDomain) {
        return NextResponse.json({ error: 'Email domain is not allowed' }, { status: 403 });
    }

    const user = await prisma.user.findUnique({
        where: { email },
    });

    if (!user || !(await bcrypt.compare(password, user.password))) {
        return NextResponse.json({ error: 'Invalid email or password' }, { status: 401 });
    }

    const token = jwt.sign({ userId: user.id }, process.env.JWT_SECRET!, { expiresIn: '1h' });

    return NextResponse.json({ token });
}