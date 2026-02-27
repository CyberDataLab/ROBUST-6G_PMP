"use client";

import React, { useState } from 'react';

const SettingsPage: React.FC = () => {
    const [emailDomain, setEmailDomain] = useState('');
    const [allowedDomains, setAllowedDomains] = useState<string[]>(['robust-6g.com']);

    const handleDomainChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setEmailDomain(e.target.value);
    };

    const handleAddDomain = () => {
        if (emailDomain && !allowedDomains.includes(emailDomain)) {
            setAllowedDomains([...allowedDomains, emailDomain]);
            setEmailDomain('');
        }
    };

    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-4">Settings</h1>
            <div className="mb-4">
                <h2 className="text-xl">Email Domain Affiliation</h2>
                <input
                    type="text"
                    value={emailDomain}
                    onChange={handleDomainChange}
                    placeholder="Add allowed email domain"
                    className="border p-2 rounded"
                />
                <button onClick={handleAddDomain} className="ml-2 bg-blue-500 text-white p-2 rounded">
                    Add Domain
                </button>
            </div>
            <div>
                <h3 className="text-lg">Allowed Domains:</h3>
                <ul>
                    {allowedDomains.map((domain, index) => (
                        <li key={index} className="list-disc ml-5">{domain}</li>
                    ))}
                </ul>
            </div>
        </div>
    );
};

export default SettingsPage;