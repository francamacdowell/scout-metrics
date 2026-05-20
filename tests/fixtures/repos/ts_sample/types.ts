export interface User {
    id: number;
    name: string;
    email: string;
    role: 'admin' | 'user' | 'guest';
}

export type ID = string | number;

export interface Repository<T> {
    findById(id: ID): T | undefined;
    findAll(): T[];
    save(entity: T): T;
    delete(id: ID): boolean;
}
