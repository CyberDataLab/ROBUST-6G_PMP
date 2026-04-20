"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError("Invalid email or password");
      } else {
        router.push("/dashboard");
        router.refresh();
      }
    } catch (err) {
      setError("An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-end justify-end overflow-hidden">
      {/* Full-screen background image */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: "url('/robust-6g-logo.jpg')" }}
      />

      {/* Dark overlay for readability */}
      <div className="absolute inset-0 bg-[#0a0e27]/75 backdrop-blur-sm" />

      {/* Gradient overlays for depth */}
      <div className="absolute inset-0 bg-gradient-to-t from-[#0a0e27] via-transparent to-[#0a0e27]/60" />
      <div className="absolute inset-0 bg-gradient-to-r from-purple-900/20 via-transparent to-cyan-900/20" />

      {/* Content — aligned to the right */}
      <div className="relative z-10 flex min-h-screen w-full max-w-md items-center px-10 pb-16">
        {/* Glass card */}
        <div className="w-full rounded-2xl border border-white/10 bg-[#0a0e27]/60 p-6 shadow-2xl backdrop-blur-xl">
          {/* Logo (small, on top of the card) */}
          <div className="mb-4 flex justify-center">
            <img
              src="/robust-6g.jpg"
              alt="ROBUST-6G"
              width={140}
              height={140}
              className="drop-shadow-2xl"
            />
          </div>

          {/* Header */}
          <div className="mb-5 text-center">
            <h3 className="text-1xl font-bold tracking-tight text-white">
              Welcome to the
              <br />
              Programmable Monitoring Platform
            </h3>
            <p className="mt-1 text-sm text-blue-200/60">
              Sign in to access your dashboard
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300 backdrop-blur-sm">
                <svg
                  className="h-5 w-5 flex-shrink-0"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                    clipRule="evenodd"
                  />
                </svg>
                {error}
              </div>
            )}

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-blue-100/80"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@robust-6g.eu"
                className="mt-1.5 block w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-black shadow-sm placeholder:text-blue-300/30 focus:border-cyan-400/50 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 backdrop-blur-sm transition-all"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-blue-100/80"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
                className="mt-1.5 block w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-black shadow-sm placeholder:text-blue-300/30 focus:border-cyan-400/50 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 backdrop-blur-sm transition-all"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-gradient-to-r from-purple-600 via-blue-600 to-cyan-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 hover:from-purple-500 hover:via-blue-500 hover:to-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:ring-offset-2 focus:ring-offset-[#0a0e27] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-300"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Signing in...
                </span>
              ) : (
                "Sign in"
              )}
            </button>

            {/* Domain policy */}
            <div className="rounded-lg border border-cyan-400/10 bg-cyan-400/5 p-3 backdrop-blur-sm">
              <p className="text-center text-xs text-cyan-200/60">
                <span className="font-medium text-cyan-200/80">
                  Organization policy:
                </span>{" "}
                Only emails affiliated with{" "}
                <span className="font-semibold text-cyan-300">ROBUST-6G</span>{" "}
                are allowed.
              </p>
              <p className="mt-1 text-center text-xs text-cyan-300/40">
                Accepted domains:{" "}
                <span className="font-mono font-medium text-cyan-300/60">
                  robust-6g.eu
                </span>
                ,{" "}
                <span className="font-mono font-medium text-cyan-300/60">
                  robust-6g.org
                </span>
              </p>
            </div>
          </form>
        </div>
      </div>

      {/* Bottom centered credit */}
      <div className="absolute bottom-6 left-0 right-0 z-10 text-center">
        <p className="text-xs text-blue-200/40">
          Development conducted by the{" "}
          <span className="font-semibold text-cyan-300/60">
            Cybersecurity and Data Science Lab
          </span>
        </p>
      </div>
    </div>
  );
}
