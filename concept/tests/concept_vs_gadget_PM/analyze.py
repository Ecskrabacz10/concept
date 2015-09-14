# This file is part of CONCEPT, the cosmological N-body code in Python.
# Copyright (C) 2015 Jeppe Mosgard Dakin.
#
# CONCEPT is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CONCEPT is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with CONCEPT. If not, see http://www.gnu.org/licenses/
#
# The auther of CONCEPT can be contacted at
# jeppe.mosgaard.dakin(at)post.au.dk
# The latest version of CONCEPT is available at
# https://github.com/jmd-dk/concept/



# This file has to be run in pure Python mode!

# Include the concept_dir in the searched paths and get directory of this file
import sys, os
sys.path.append(os.environ['concept_dir'])
this_dir = os.path.dirname(os.path.realpath(__file__))

# Imports from the CONCEPT code
from commons import *
from IO import GadgetSnapshot

# Use a matplotlib backend that does not require a running X-server
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Determine the number of snapshots from the outputlist file
N_snapshots = np.loadtxt(this_dir + '/outputlist').size

# Instantiate a GadgetSnapshot instance which will be reused for all GADGET snapshots
snapshot = GadgetSnapshot()

# Read in data from the CONCEPT snapshots
a = []
particles = []
for fname in ('snapshot_a=1.00', ):
    snapshot.load(this_dir + '/output/' + fname, write_msg=False)
    a.append(snapshot.header['Time'])
    particles.append(snapshot.particles)

# Read in data from the GADGET snapshots
a_gadget = []
particles_gadget = []
for i in range(N_snapshots):
    snapshot.load(this_dir + '/output/snapshot_gadget_' + '0'*(3-len(str(i))) + str(i), write_msg=False)
    a_gadget.append(snapshot.header['Time'])
    particles_gadget.append(snapshot.particles)

# Using the particle order of CONCEPT as the standard, find the corresponding
# ID's in the GADGET snapshots and order these particles accoringly.
N = particles[0].N
D2 = zeros(N)
ID = zeros(N, dtype='int')
for i in range(N_snapshots):
    x = particles[i].posx
    y = particles[i].posy
    z = particles[i].posz
    x_gadget = particles_gadget[i].posx
    y_gadget = particles_gadget[i].posy
    z_gadget = particles_gadget[i].posz
    for j in range(N):
        for k in range(N):
            dx = x[j] - x_gadget[k]
            if dx > half_boxsize:
                dx -= boxsize
            elif dx < -half_boxsize:
                dx += boxsize
            dy = y[j] - y_gadget[k]
            if dy > half_boxsize:
                dy -= boxsize
            elif dy < -half_boxsize:
                dy += boxsize
            dz = z[j] - z_gadget[k]
            if dz > half_boxsize:
                dz -= boxsize
            elif dz < -half_boxsize:
                dz += boxsize
            D2[k] = dx**2 + dy**2 + dz**2
        ID[j] = np.argmin(D2)
    particles_gadget[i].posx = particles_gadget[i].posx[ID]
    particles_gadget[i].posy = particles_gadget[i].posy[ID]
    particles_gadget[i].posz = particles_gadget[i].posz[ID]
    particles_gadget[i].momx = particles_gadget[i].momx[ID]
    particles_gadget[i].momy = particles_gadget[i].momy[ID]
    particles_gadget[i].momz = particles_gadget[i].momz[ID]

# Compute distance between particles in the two snapshots
fig_file = this_dir + '/result.pdf'
x = particles[-1].posx
y = particles[-1].posy
z = particles[-1].posz
x_gadget = particles_gadget[-1].posx
y_gadget = particles_gadget[-1].posy
z_gadget = particles_gadget[-1].posz
dist = sqrt(array([min([(x[i] - x_gadget[i] + xsgn*boxsize)**2 + (y[i] - y_gadget[i] + ysgn*boxsize)**2 + (z[i] - z_gadget[i] + zsgn*boxsize)**2 for xsgn in (-1, 0, +1) for ysgn in (-1, 0, 1) for zsgn in (-1, 0, 1)]) for i in range(N)]))

# Plot
plt.plot(dist/boxsize, 'sr')
plt.xlabel('Particle number')
plt.ylabel('$|\mathbf{x}_{\mathrm{CONCEPT}} - \mathbf{x}_{\mathrm{GADGET}}|/\mathrm{boxsize}$')
plt.xlim(0, N -1)
plt.ylim(0, 1)
plt.savefig(fig_file)

# Printout error message for unsuccessful test
tol = 1e-3
if np.mean(dist/boxsize) > tol:
    masterwarn('The results from CONCEPT disagree with those from GADGET.\n'
               + 'See "{}" for a visualization.'.format(fig_file))
    sys.exit(1)

