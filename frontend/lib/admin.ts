type AdminUserLike = {
    email?: string;
    userMetadata?: {
        is_admin?: boolean;
        role?: string;
        roles?: unknown;
    };
    appMetadata?: {
        is_admin?: boolean;
        role?: string;
        roles?: unknown;
    };
};

export function getAdminEmailsFromEnv() {
    const raw = process.env.NEXT_PUBLIC_ADMIN_EMAILS || '';
    if (!raw.trim()) return [];
    return raw
        .split(',')
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean);
}

function hasAdminRole(value: unknown): boolean {
    if (typeof value === 'string') {
        const role = value.trim().toLowerCase();
        return role === 'admin' || role === 'owner';
    }
    if (Array.isArray(value)) {
        return value.some((item) => hasAdminRole(item));
    }
    return false;
}

export function isAdminUser(user: AdminUserLike | null | undefined, adminEmails: string[]): boolean {
    if (!user) return false;
    const email = String(user.email || '').trim().toLowerCase();
    if (email && adminEmails.includes(email)) return true;

    const userMeta = user.userMetadata || {};
    const appMeta = user.appMetadata || {};
    if (Boolean(userMeta.is_admin) || Boolean(appMeta.is_admin)) return true;
    if (hasAdminRole(userMeta.role) || hasAdminRole(appMeta.role)) return true;
    if (hasAdminRole(userMeta.roles) || hasAdminRole(appMeta.roles)) return true;
    return false;
}
