import { createMocks } from 'node-mocks-http';
import { loginHandler, registerHandler } from '../../../src/app/api/auth/login/route';
import { prisma } from '../../../src/lib/prisma';

jest.mock('../../../src/lib/prisma');

describe('Auth API', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('POST /api/auth/login', () => {
    it('should return 200 and a token for valid credentials', async () => {
      const { req, res } = createMocks({
        method: 'POST',
        body: {
          email: 'test@robust-6g.com',
          password: 'password123',
        },
      });

      prisma.user.findUnique.mockResolvedValueOnce({
        id: 1,
        email: 'test@robust-6g.com',
        password: 'hashedPassword',
      });

      await loginHandler(req, res);

      expect(res._getStatusCode()).toBe(200);
      expect(res._getData()).toHaveProperty('token');
    });

    it('should return 401 for invalid credentials', async () => {
      const { req, res } = createMocks({
        method: 'POST',
        body: {
          email: 'wrong@robust-6g.com',
          password: 'wrongPassword',
        },
      });

      prisma.user.findUnique.mockResolvedValueOnce(null);

      await loginHandler(req, res);

      expect(res._getStatusCode()).toBe(401);
      expect(res._getData()).toHaveProperty('error', 'Invalid credentials');
    });
  });

  describe('POST /api/auth/register', () => {
    it('should return 201 for successful registration', async () => {
      const { req, res } = createMocks({
        method: 'POST',
        body: {
          email: 'newuser@robust-6g.com',
          password: 'newPassword123',
        },
      });

      prisma.user.create.mockResolvedValueOnce({
        id: 2,
        email: 'newuser@robust-6g.com',
      });

      await registerHandler(req, res);

      expect(res._getStatusCode()).toBe(201);
      expect(res._getData()).toHaveProperty('message', 'User registered successfully');
    });

    it('should return 400 for email already in use', async () => {
      const { req, res } = createMocks({
        method: 'POST',
        body: {
          email: 'existing@robust-6g.com',
          password: 'password123',
        },
      });

      prisma.user.findUnique.mockResolvedValueOnce({
        id: 1,
        email: 'existing@robust-6g.com',
      });

      await registerHandler(req, res);

      expect(res._getStatusCode()).toBe(400);
      expect(res._getData()).toHaveProperty('error', 'Email already in use');
    });
  });
});