import type { User, ID, Repository } from './types';

class InMemoryUserRepository implements Repository<User> {
    private users: Map<ID, User> = new Map();

    findById(id: ID): User | undefined {
        return this.users.get(id);
    }

    findAll(): User[] {
        return Array.from(this.users.values());
    }

    save(user: User): User {
        this.users.set(user.id, user);
        return user;
    }

    delete(id: ID): boolean {
        return this.users.delete(id);
    }
}

export class UserService {
    constructor(private readonly repo: Repository<User>) {}

    createUser(name: string, email: string, role: User['role'] = 'user'): User {
        const id = Date.now();
        const user: User = { id, name, email, role };
        return this.repo.save(user);
    }

    getUser(id: ID): User {
        const user = this.repo.findById(id);
        if (!user) {
            throw new Error(`User ${id} not found`);
        }
        return user;
    }

    listAdmins(): User[] {
        return this.repo.findAll().filter(u => u.role === 'admin');
    }

    promoteToAdmin(id: ID): User {
        const user = this.getUser(id);
        const updated: User = { ...user, role: 'admin' };
        return this.repo.save(updated);
    }
}

export function createDefaultRepository(): InMemoryUserRepository {
    return new InMemoryUserRepository();
}
