import { validateEmailDomain } from '../../src/policies/emailDomainAffiliation';

describe('Email Domain Affiliation Policy', () => {
  const allowedDomains = ['robust-6g.com', 'robust-6g.org'];

  test('should allow valid email domain', () => {
    const email = 'user@robust-6g.com';
    expect(validateEmailDomain(email, allowedDomains)).toBe(true);
  });

  test('should allow valid email domain with subdomain', () => {
    const email = 'user@sub.robust-6g.com';
    expect(validateEmailDomain(email, allowedDomains)).toBe(true);
  });

  test('should deny invalid email domain', () => {
    const email = 'user@notallowed.com';
    expect(validateEmailDomain(email, allowedDomains)).toBe(false);
  });

  test('should deny email without domain', () => {
    const email = 'user@';
    expect(validateEmailDomain(email, allowedDomains)).toBe(false);
  });

  test('should deny email without @ symbol', () => {
    const email = 'user.robust-6g.com';
    expect(validateEmailDomain(email, allowedDomains)).toBe(false);
  });
});