import { NextApiRequest, NextApiResponse } from 'next';

const ALLOWED_DOMAINS = ['robust-6g.com', 'robust-6g.org'];

export const validateEmailDomain = (email: string): boolean => {
    const domain = email.split('@')[1];
    return ALLOWED_DOMAINS.includes(domain);
};

export const emailDomainAffiliationPolicy = (req: NextApiRequest, res: NextApiResponse, next: () => void) => {
    const email = req.body.email;

    if (!email || !validateEmailDomain(email)) {
        return res.status(403).json({ message: 'Email domain is not allowed.' });
    }

    next();
};