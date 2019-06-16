# This file is part of CO𝘕CEPT, the cosmological 𝘕-body code in Python.
# Copyright © 2015–2019 Jeppe Mosgaard Dakin.
#
# CO𝘕CEPT is free software: You can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CO𝘕CEPT is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with CO𝘕CEPT. If not, see http://www.gnu.org/licenses/
#
# The author of CO𝘕CEPT can be contacted at dakin(at)phys.au.dk
# The latest version of CO𝘕CEPT is available at
# https://github.com/jmd-dk/concept/



# Import everything from the commons module.
# In the .pyx file, Cython declared variables will also get cimported.
from commons import *

# Cython imports
cimport('from ewald import ewald')
cimport('from communication import '
    'domain_subdivisions, domain_start_x, domain_start_y, domain_start_z, '
    'domain_size_x, domain_size_y, domain_size_z, '
)



# Function responsible for constructing pairings between subtiles within
# the supplied subtiling. Subtiles further away than the supplied cutoff
# will not be paired.
@cython.header(
    # Arguments
    subtiling='Tiling',
    cutoff='double',
    # Locals
    all_pairings='Py_ssize_t***',
    all_pairings_N='Py_ssize_t**',
    dim='int',
    pairing_index='Py_ssize_t',
    pairings='Py_ssize_t**',
    pairings_N='Py_ssize_t*',
    pairings_r='Py_ssize_t*',
    r_dim='Py_ssize_t',
    r2='double',
    same_tile='bint',
    subtile_index_r='Py_ssize_t',
    subtile_index_s='Py_ssize_t',
    subtile_index3D='Py_ssize_t[::1]',
    subtile_index3D_r='Py_ssize_t[::1]',
    subtile_index3D_s='Py_ssize_t[::1]',
    subtile_pairings_index='Py_ssize_t',
    tile_pair_index='Py_ssize_t',
    tiles_offset='Py_ssize_t[::1]',
    tiles_offset_i='Py_ssize_t',
    tiles_offset_j='Py_ssize_t',
    tiles_offset_k='Py_ssize_t',
    returns='Py_ssize_t',
)
def get_subtile_pairings(subtiling, cutoff):
    global subtile_pairings_cache, subtile_pairings_N_cache, subtile_pairings_cache_size
    # Get index of the required subtile pairings in the global cache.
    subtile_pairings_index = subtile_pairings_cache_indices.get(
        (subtiling, cutoff), subtile_pairings_cache_size,
    )
    # Return cached results in form of the cache index
    if subtile_pairings_index < subtile_pairings_cache_size:
        return subtile_pairings_index
    # No cached results found.
    # Create subtile pairings for each of the 27 cases
    # of neighbour tiles.
    all_pairings   = malloc(27*sizeof('Py_ssize_t**'))
    all_pairings_N = malloc(27*sizeof('Py_ssize_t*'))
    tiles_offset      = empty(3, dtype=C2np['Py_ssize_t'])
    subtile_index3D_r = empty(3, dtype=C2np['Py_ssize_t'])
    for tiles_offset_i in range(-1, 2):
        tiles_offset[0] = tiles_offset_i
        for tiles_offset_j in range(-1, 2):
            tiles_offset[1] = tiles_offset_j
            for tiles_offset_k in range(-1, 2):
                tiles_offset[2] = tiles_offset_k
                # Does the tile offset correspond to
                # a tile being paired with itself?
                same_tile = (tiles_offset_i == tiles_offset_j == tiles_offset_k == 0)
                # Get 1D tile pair index from the 3D offset
                tile_pair_index = get_neighbourtile_pair_index(tiles_offset)
                # Allocate memory for subtile pairings
                # for this particular tile pair.
                pairings   = malloc(subtiling.size*sizeof('Py_ssize_t*'))
                pairings_N = malloc(subtiling.size*sizeof('Py_ssize_t'))
                all_pairings  [tile_pair_index] = pairings
                all_pairings_N[tile_pair_index] = pairings_N
                # Loop over all receiver subtiles
                for subtile_index_r in range(subtiling.size):
                    # Get 3D subtile index. As the tile_index3D() method
                    # return a view over internal data and we mutate
                    # subtile_index3D_r below, we take a copy of the
                    # returned data.
                    subtile_index3D = subtiling.tile_index3D(subtile_index_r)
                    for dim in range(3):
                        subtile_index3D_r[dim] = subtile_index3D[dim]
                    # The receiver and supplier subtiles belong to
                    # (potentially) diffent tiles, with a relative
                    # offset given by tiles_offset_*, so that the
                    # supplier tile is at the receiver tile location
                    # plus tiles_offset_*. We now subtract this offset
                    # from the receiver 3D subtile index, so that the
                    # difference in subtile indices between the receiver
                    # and supplier subtile is proportional to their
                    # physical separation. Note that subtile_index3D_r
                    # no longer represents the actual index in memory.
                    for dim in range(3):
                        subtile_index3D_r[dim] -= tiles_offset[dim]*subtiling.shape[dim]
                    # Allocate memory for subtile pairings with this
                    # particular receiver subilte.
                    # We give it the maximum possible needed memory.
                    pairings_r = malloc(subtiling.size*sizeof('Py_ssize_t'))
                    pairings[subtile_index_r] = pairings_r
                    # Pair receiver subtile with every supplier subtile,
                    # unless the tile is being paired with itself.
                    # In that case, we need to not double count the
                    # subtile pairing (while still pairing every subtile
                    # with themselves).
                    pairing_index = 0
                    for subtile_index_s in range(
                        subtile_index_r if same_tile else 0,
                        subtiling.size,
                    ):
                        subtile_index3D_s = subtiling.tile_index3D(subtile_index_s)
                        # Measure (squared) distance between the subtile
                        # pair and reject if larger than the passed
                        # cutoff length.
                        r2 = 0
                        for dim in range(3):
                            # Distance between the same point in the two
                            # subtiles along the dim'th dimenson,
                            # in subtile grid units.
                            r_dim = abs(subtile_index3D_r[dim] - subtile_index3D_s[dim])
                            if r_dim > 0:
                                # The two subtiles are offset along the
                                # dim'th dimension. Subtract one unit
                                # from the length, making the length
                                # between the closest two points
                                # in the two subtiles.
                                r_dim -= 1
                            r2 += (r_dim*subtiling.tile_extent[dim])**2
                        if r2 > ℝ[cutoff**2]:
                            continue
                        # Add this supplier subtile to the list of
                        # pairing partners for this receiver subtile.
                        pairings_r[pairing_index] = subtile_index_s
                        pairing_index += 1
                    # All pairs found for this receiver subtile.
                    # Truncate the allocated memory as to only contain
                    # the used chunk.
                    pairings[subtile_index_r] = realloc(
                        pairings_r, pairing_index*sizeof('Py_ssize_t'),
                    )
                    # Record the size of this pairing array
                    pairings_N[subtile_index_r] = pairing_index
    # Store results in global caches
    subtile_pairings_cache_size += 1
    subtile_pairings_cache = realloc(
        subtile_pairings_cache, subtile_pairings_cache_size*sizeof('Py_ssize_t***'),
    )
    subtile_pairings_N_cache = realloc(
        subtile_pairings_N_cache, subtile_pairings_cache_size*sizeof('Py_ssize_t**'),
    )
    subtile_pairings_cache  [subtile_pairings_index] = all_pairings
    subtile_pairings_N_cache[subtile_pairings_index] = all_pairings_N
    subtile_pairings_cache_indices[subtiling, cutoff] = subtile_pairings_index
    # Return cached results in form of the cache index
    return subtile_pairings_index
# Caches used by the get_subtile_pairings function
cython.declare(
    subtile_pairings_cache_size='Py_ssize_t',
    subtile_pairings_cache_indices=dict,
    subtile_pairings_cache='Py_ssize_t****',
    subtile_pairings_N_cache='Py_ssize_t***',
)
subtile_pairings_cache_size = 0
subtile_pairings_cache_indices = {}
subtile_pairings_cache   = malloc(subtile_pairings_cache_size*sizeof('Py_ssize_t***'))
subtile_pairings_N_cache = malloc(subtile_pairings_cache_size*sizeof('Py_ssize_t**'))

# Helper function for the get_subtile_pairings function
@cython.header(
    # Arguments
    tiles_offset='Py_ssize_t[::1]',
    # Locals
    dim='int',
    returns='Py_ssize_t',
)
def get_neighbourtile_pair_index(tiles_offset):
    # The passed tiles_offset is the relative offset between a pair of
    # neighbouring tiles, and so each of its three elements has to be
    # in {-1, 0, +1}. If any element is outside this range, it is due
    # to the periodic boundaries. Fix this now, as we do not care about
    # whether the tile pair is connected through the box boundary.
    for dim in range(3):
        if tiles_offset[dim] > 1:
            tiles_offset[dim] = -1
        elif tiles_offset[dim] < -1:
            tiles_offset[dim] = +1
    # Compute 1D index from a 3×3×3 shape. We add 1 to each element,
    # as they range from -1 to +1.
    return ((tiles_offset[0] + 1)*3 + (tiles_offset[1] + 1))*3 + (tiles_offset[2] + 1)

# Generic function implementing particle-particle pairing.
# Note that this function returns a generator and so should only be
# called within a loop. See gravity_pairwise() for an example.
@cython.iterator
def particle_particle(
    receiver, supplier, pairing_level,
    tile_indices_receiver, tile_indices_supplier,
    rank_supplier, interaction_name, only_supply,
):
    # Cython declarations for variables used for the iteration,
    # not including those to yield.
    # Do not write these using the decorator syntax above this function.
    cython.declare(
        N_subtiles='Py_ssize_t',
        all_subtile_pairings='Py_ssize_t***',
        all_subtile_pairings_N='Py_ssize_t**',
        dim='int',
        highest_populated_rung_r='signed char',
        highest_populated_rung_s='signed char',
        lowest_active_rung_r='signed char',
        lowest_active_rung_s='signed char',
        lowest_populated_rung_r='signed char',
        lowest_populated_rung_s='signed char',
        posx_r='double*',
        posx_s='double*',
        posy_r='double*',
        posy_s='double*',
        posz_r='double*',
        posz_s='double*',
        rung_index_s_start='signed char',
        rung_particle_index_r='Py_ssize_t',
        rung_particle_index_s='Py_ssize_t',
        rung_particle_index_s_start='Py_ssize_t',
        rung_N_r='Py_ssize_t',
        rung_N_s='Py_ssize_t',
        rung_index_r='signed char',
        rung_index_s='signed char',
        rung_jump_r='signed char',
        rung_jump_s='signed char',
        rung_jumps_r='signed char*',
        rung_jumps_s='signed char*',
        rung_r='Py_ssize_t*',
        rung_s='Py_ssize_t*',
        rungs_N_r='Py_ssize_t*',
        rungs_N_s='Py_ssize_t*',
        subtile_index_r='Py_ssize_t',
        subtile_index_s='Py_ssize_t',
        subtile_pairings='Py_ssize_t**',
        subtile_pairings_N='Py_ssize_t*',
        subtile_pairings_N_r='Py_ssize_t',
        subtile_pairings_index='Py_ssize_t',
        subtile_pairings_r='Py_ssize_t*',
        subtile_r='Py_ssize_t**',
        subtile_s='Py_ssize_t**',
        subtiles_contain_particles_r='signed char*',
        subtiles_contain_particles_s='signed char*',
        subtiles_r='Py_ssize_t***',
        subtiles_rungs_N_r='Py_ssize_t**',
        subtiles_rungs_N_s='Py_ssize_t**',
        subtiles_s='Py_ssize_t***',
        subtiling_name=str,
        subtiling_name_2=str,
        subtiling_r='Tiling',
        subtiling_s='Tiling',
        subtiling_s_2='Tiling',
        tile_extent='double[::1]',
        tile_index_r='Py_ssize_t',
        tile_index_s='Py_ssize_t',
        tile_index3D_r='Py_ssize_t[::1]',
        tile_index3D_s='Py_ssize_t[::1]',
        tile_pair_index='Py_ssize_t',
        tiles_contain_particles_r='signed char*',
        tiles_contain_particles_s='signed char*',
        tiles_r='Py_ssize_t***',
        tiles_s='Py_ssize_t***',
        tiling_location_r='double[::1]',
        tiling_location_s='double[::1]',
        tiling_name=str,
        tiling_r='Tiling',
        tiling_s='Tiling',
        xi='double',
        yi='double',
        zi='double',
    )
    # Extract particle variables from the receiver component
    posx_r = receiver.posx
    posy_r = receiver.posy
    posz_r = receiver.posz
    lowest_active_rung_r     = receiver.lowest_active_rung
    lowest_populated_rung_r  = receiver.lowest_populated_rung
    highest_populated_rung_r = receiver.highest_populated_rung
    # Extract particle variables from the supplier
    # (the external) component.
    posx_s = supplier.posx
    posy_s = supplier.posy
    posz_s = supplier.posz
    lowest_active_rung_s     = supplier.lowest_active_rung
    lowest_populated_rung_s  = supplier.lowest_populated_rung
    highest_populated_rung_s = supplier.highest_populated_rung
    rung_jumps_r = receiver.rung_jumps
    rung_jumps_s = supplier.rung_jumps
    # The names used to refer to the domain and tile level tiling
    # (tiles and subtiles). In the case of pairing_level == 'domain',
    # we always use the trivial tiling.
    if ℤ[pairing_level == 'tile']:
        tiling_name    = f'{interaction_name} (tiles)'
        subtiling_name = f'{interaction_name} (subtiles)'
    else:  # pairing_level == 'domain':
        tiling_name = subtiling_name = 'trivial'
    # Extract tiling variables from receiver
    tiling_r = receiver.tilings[tiling_name]
    tiling_location_r         = tiling_r.location
    tile_extent               = tiling_r.tile_extent  # The same for receiver and supplier
    tiles_r                   = tiling_r.tiles
    tiles_contain_particles_r = tiling_r.contain_particles
    subtiling_r = receiver.tilings[subtiling_name]
    subtiles_r                   = subtiling_r.tiles
    subtiles_contain_particles_r = subtiling_r.contain_particles
    N_subtiles                   = subtiling_r.size  # The same for receiver and supplier
    # Extract tiling variables from supplier
    tiling_s = supplier.tilings[tiling_name]
    tiling_location_s         = tiling_s.location
    tiles_s                   = tiling_s.tiles
    tiles_contain_particles_s = tiling_s.contain_particles
    subtiling_s = supplier.tilings[subtiling_name]
    subtiles_s                   = subtiling_s.tiles
    subtiles_contain_particles_s = subtiling_s.contain_particles
    # When the receiver and supplier components are the same
    # and the receiver and supplier domains are also the same,
    # we now have a case where (tiling_r is tiling_s) and
    # (subtiling_r is subtiling_s) are both True. This is OK for
    # the coarse tiling, but not for the subtiling, as here we need
    # to re-sort the particles during the iteration below. That is,
    # we need to keep track of the sorting of the receiver tiles
    # into subtiles while also keeping track of the sorting of the
    # supplier tiles into subtiles. We thus always need two separate
    # subtiling_{r/s} instances, which we do not have in the case
    # mentioned. When this is the case, we make use of a second,
    # separate Tiling instance. If however the subtiling in use is the
    # trivial tiling, the re-sorting has no effect, and so we do not
    # have to worry.
    if 𝔹[receiver.name == supplier.name and rank == rank_supplier and subtiling_name != 'trivial']:
        subtiling_name_2 = f'{interaction_name} (subtiles 2)'
        if subtiling_name_2 not in supplier.tilings:
            supplier.tilings.pop(subtiling_name)
            subtiling_s_2 = supplier.init_tiling(subtiling_name)
            supplier.tilings[subtiling_name  ] = subtiling_s
            supplier.tilings[subtiling_name_2] = subtiling_s_2
        subtiling_s = supplier.tilings[subtiling_name_2]
        subtiles_s                   = subtiling_s.tiles
        subtiles_contain_particles_s = subtiling_s.contain_particles
    # Get subtile pairings between each
    # of the 27 possible tile pairings.
    subtile_pairings_index = get_subtile_pairings(
        subtiling_r, shortrange_params[interaction_name]['cutoff'],
    )
    all_subtile_pairings   = subtile_pairings_cache  [subtile_pairings_index]
    all_subtile_pairings_N = subtile_pairings_N_cache[subtile_pairings_index]
    # Flags specifying whether the force betweeen particle i and j
    # should be applied to i and j. If only_supply is True,
    # the values below are correct. Otherwise, other values
    # will be set further down.
    apply_to_i = True
    apply_to_j = False
    # Loop over the requested tiles in the receiver
    for tile_index_r in range(ℤ[tile_indices_receiver.shape[0]]):
        tile_index_r = tile_indices_receiver[tile_index_r]
        # Skip tile if it does not contain any particles at all,
        # or only inactive particles when only_supply is True.
        with unswitch(1):
            if 𝔹[not only_supply]:
                if tiles_contain_particles_r[tile_index_r] == 0:
                    continue
            else:
                if tiles_contain_particles_r[tile_index_r] != 2:
                    continue
        # Sort particles within the receiver tile into subtiles
        tile_index3D_r = tiling_r.tile_index3D(tile_index_r)
        for dim in range(3):
            tile_location_r[dim] = tiling_location_r[dim] + tile_index3D_r[dim]*tile_extent[dim]
        subtiling_r.relocate(tile_location_r)
        subtiling_r.sort(tiling_r, tile_index_r)
        subtiles_rungs_N_r = subtiling_r.tiles_rungs_N
        # Loop over the requested tiles in the supplier
        for tile_index_s in range(ℤ[tile_indices_supplier.shape[0]]):
            tile_index_s = tile_indices_supplier[tile_index_s]
            # Skip tile if it does not contain any particles at all
            if tiles_contain_particles_s[tile_index_s] == 0:
                continue
            # Sort particles within the supplier tile into subtiles
            tile_index3D_s = tiling_s.tile_index3D(tile_index_s)
            for dim in range(3):
                tile_location_s[dim] = (
                    tiling_location_s[dim] + tile_index3D_s[dim]*tile_extent[dim]
                )
            subtiling_s.relocate(tile_location_s)
            subtiling_s.sort(tiling_s, tile_index_s)
            subtiles_rungs_N_s = subtiling_s.tiles_rungs_N
            # Get the needed subtile pairings for the selected receiver
            # and supplier tiles (which should be neighbour tiles).
            for dim in range(3):
                tiles_offset[dim] = tile_index3D_s[dim] - tile_index3D_r[dim]
            tile_pair_index = get_neighbourtile_pair_index(tiles_offset)
            subtile_pairings   = all_subtile_pairings  [tile_pair_index]
            subtile_pairings_N = all_subtile_pairings_N[tile_pair_index]
            # Loop over all subtiles in the selected receiver tile
            for subtile_index_r in range(N_subtiles):
                # Skip subtile if it does not contain
                # any particles at all, or only inactive particles
                # when only_supply is True.
                with unswitch(3):
                    if 𝔹[not only_supply]:
                        if subtiles_contain_particles_r[subtile_index_r] == 0:
                            continue
                    else:
                        if subtiles_contain_particles_r[subtile_index_r] != 2:
                            continue
                subtile_r = subtiles_r[subtile_index_r]
                rungs_N_r = subtiles_rungs_N_r[subtile_index_r]
                subtile_pairings_r   = subtile_pairings  [subtile_index_r]
                subtile_pairings_N_r = subtile_pairings_N[subtile_index_r]
                # Loop over the needed supplier subtiles
                for subtile_index_s in range(subtile_pairings_N_r):
                    subtile_index_s = subtile_pairings_r[subtile_index_s]
                    # Skip subtile if it does not contain
                    # any particles at all.
                    if subtiles_contain_particles_s[subtile_index_s] == 0:
                        continue
                    subtile_s = subtiles_s[subtile_index_s]
                    rungs_N_s = subtiles_rungs_N_s[subtile_index_s]
                    # Loop over all rungs in the receiver subtile
                    for rung_index_r in range(
                        ℤ[lowest_active_rung_r if only_supply else lowest_populated_rung_r],
                        ℤ[highest_populated_rung_r + 1],
                    ):
                        rung_N_r = rungs_N_r[rung_index_r]
                        if rung_N_r == 0:
                            continue
                        rung_r = subtile_r[rung_index_r]
                        # We need to pair all active receiver rungs
                        # with all supplier rungs. All inactive
                        # receiver rungs need only to be paired with
                        # the active supplier rungs (i.e. we do not need
                        # to pair up two inacive rungs).
                        # If only_supply is True, the values already set
                        # will be used.
                        rung_index_s_start = lowest_populated_rung_s
                        with unswitch(5):
                            if 𝔹[not only_supply]:
                                # The supplier should receive
                                # a kick as well.
                                if rung_index_r < lowest_active_rung_r:
                                    # Only the supplier should receive
                                    # a kick.
                                    apply_to_i = False
                                    rung_index_s_start = lowest_active_rung_s
                                else:
                                    # The receiver and the supplier
                                    # should receive a kick.
                                    apply_to_i = True
                        # We need to make sure not to double count the
                        # rung pairs for local interactions. Here,
                        # local means that the current components,
                        # domains, tiles and subtiles for the receiver
                        # and supplier are all the same.
                        with unswitch(5):
                            if 𝔹[receiver.name == supplier.name and rank == rank_supplier]:
                                with unswitch(3):
                                    if 𝔹[tile_index_r == tile_index_s]:
                                        with unswitch(1):
                                            if 𝔹[subtile_index_r == subtile_index_s]:
                                                if rung_index_s_start < rung_index_r:
                                                    rung_index_s_start = rung_index_r
                        # Loop over the needed supplier rungs
                        for rung_index_s in range(
                            rung_index_s_start, ℤ[highest_populated_rung_s + 1]
                        ):
                            rung_N_s = rungs_N_s[rung_index_s]
                            if rung_N_s == 0:
                                continue
                            rung_s = subtile_s[rung_index_s]
                            # Flag whether we need to apply the force to
                            # the supplier particles in this rung (if
                            # not, we still apply the force to the
                            # receiver particles).
                            with unswitch(6):
                                if 𝔹[not only_supply]:
                                    apply_to_j = (rung_index_s >= lowest_active_rung_s)
                            # Loop over all particles
                            # in the receiver rung.
                            for rung_particle_index_r in range(rung_N_r):
                                # Get receiver particle index
                                i = rung_r[rung_particle_index_r]
                                # Construct rung_index_i. This is equal
                                # to rung_index_r, except for when a
                                # particle jump to another rung.
                                # In this case, rung_index_i no longer
                                # corresponds to any actual rung,
                                # but it can be used to correctly index
                                # into arrays of time step integrals.
                                if True:  #with unswitch(7):
                                    if 𝔹[receiver.use_rungs]:
                                        rung_jump_r = rung_jumps_r[i]
                                        if rung_jump_r == 0:
                                            # Particle i stays
                                            # at its current rung.
                                            rung_index_i = rung_index_r
                                        elif rung_jump_r == +1:
                                            # Particle i jumps up to rung
                                            # rung_index_r + 1.
                                            rung_index_i = rung_index_r + ℤ[2*N_rungs]
                                        else:  # rung_jump_r == -1
                                            # Particle i jumps down to rung
                                            # rung_index_r - 1.
                                            rung_index_i = rung_index_r + N_rungs
                                    else:
                                        rung_index_i = rung_index_r
                                # Get coordinates of receiver particle
                                xi = posx_r[i]
                                yi = posy_r[i]
                                zi = posz_r[i]
                                # We need to make sure not to double
                                # count the particle pairs for local
                                # interactions. Here, local means that
                                # the current components, domains,
                                # tiles, subtiles and rungs for the
                                # receiver and supplier are all
                                # the same.
                                rung_particle_index_s_start = 0
                                with unswitch(7):
                                    if 𝔹[receiver.name == supplier.name and rank == rank_supplier]:
                                        with unswitch(5):
                                            if 𝔹[tile_index_r == tile_index_s]:
                                                with unswitch(3):
                                                    if 𝔹[subtile_index_r == subtile_index_s]:
                                                        with unswitch(1):
                                                            if 𝔹[rung_index_r == rung_index_s]:
                                                                rung_particle_index_s_start = (
                                                                    rung_particle_index_r + 1
                                                                )
                                # Loop over the needed particles
                                # in the supplier rung.
                                for rung_particle_index_s in range(
                                    rung_particle_index_s_start, rung_N_s,
                                ):
                                    # Get supplier particle index
                                    j = rung_s[rung_particle_index_s]
                                    # Construct rung_index_j
                                    if True:  # with unswitch(8):
                                        if 𝔹[not only_supply and supplier.use_rungs]:
                                            rung_jump_s = rung_jumps_s[j]
                                            if rung_jump_s == 0:
                                                # Particle j stays
                                                # at its current rung.
                                                rung_index_j = rung_index_s
                                            elif rung_jump_s == +1:
                                                # Particle j jumps up to
                                                # rung rung_index_s + 1.
                                                rung_index_j = rung_index_s + ℤ[2*N_rungs]
                                            else:  # rung_jump_s == -1
                                                # Particle j jumps
                                                # down to rung
                                                # rung_index_s - 1.
                                                rung_index_j = rung_index_s + N_rungs
                                        else:
                                            rung_index_j = rung_index_s
                                    # "Vector" from particle j
                                    # to particle i.
                                    x_ji = xi - posx_s[j]
                                    y_ji = yi - posy_s[j]
                                    z_ji = zi - posz_s[j]
                                    # Yield the needed variables
                                    yield i, j, rung_index_i, rung_index_j, x_ji, y_ji, z_ji, apply_to_i, apply_to_j
# Variables used by the particle_particle function
cython.declare(
    tile_location_r='double[::1]',
    tile_location_s='double[::1]',
    tiles_offset='Py_ssize_t[::1]',
)
tile_location_r = empty(3, dtype=C2np['double'])
tile_location_s = empty(3, dtype=C2np['double'])
tiles_offset    = empty(3, dtype=C2np['Py_ssize_t'])

# Function implementing pairwise gravity (full/periodic)
@cython.header(
    # Arguments
    receiver='Component',
    supplier='Component',
    pairing_level=str,
    tile_indices_receiver='Py_ssize_t[::1]',
    tile_indices_supplier='Py_ssize_t[::1]',
    rank_supplier='int',
    only_supply='bint',
    ᔑdt=dict,
    extra_args=dict,
    # Locals
    apply_to_i='bint',
    apply_to_j='bint',
    force_ij='double*',
    forcex_ij='double',
    forcey_ij='double',
    forcez_ij='double',
    gravity_factor='double',
    gravity_factors='double[::1]',
    i='Py_ssize_t',
    interaction_name=str,
    j='Py_ssize_t',
    momx_r='double*',
    momx_s='double*',
    momy_r='double*',
    momy_s='double*',
    momz_r='double*',
    momz_s='double*',
    r3='double',
    rung_index_i='signed char',
    rung_index_j='signed char',
    x_ji='double',
    y_ji='double',
    z_ji='double',
    Δmomx_s='double*',
    Δmomy_s='double*',
    Δmomz_s='double*',
    returns='void',
)
def gravity_pairwise(
    receiver, supplier, pairing_level,
    tile_indices_receiver, tile_indices_supplier,
    rank_supplier, only_supply, ᔑdt, extra_args,
):
    # Extract variables from the receiver component
    momx_r = receiver.momx
    momy_r = receiver.momy
    momz_r = receiver.momz
    # Extract variables from the supplier (the external) component
    momx_s  = supplier.momx
    momy_s  = supplier.momy
    momz_s  = supplier.momz
    Δmomx_s = supplier.Δmomx
    Δmomy_s = supplier.Δmomy
    Δmomz_s = supplier.Δmomz
    # Construct array of factors used for momentum updates:
    #   Δmom = -r⃗/r³*G*mass_r*mass_s*Δt/a.
    # In the general case of decaying particles,
    # the mass of each particle is
    #   mass(a) = component.mass*a**(-3*component.w_eff(a=a)).
    # Below we integrate over the time dependence.
    # The array should be indexed with the rung_index
    # of the receiver particle.
    gravity_factors = G_Newton*receiver.mass*supplier.mass*ᔑdt[
        'a**(-3*w_eff₀-3*w_eff₁-1)', receiver.name, supplier.name]
    # Loop over all (receiver, supplier) particle pairs (i, j)
    interaction_name = 'gravity'
    for i, j, rung_index_i, rung_index_j, x_ji, y_ji, z_ji, apply_to_i, apply_to_j in particle_particle(
        receiver, supplier, pairing_level,
        tile_indices_receiver, tile_indices_supplier,
        rank_supplier, interaction_name, only_supply,
    ):
        # Translate coordinates so they correspond to the nearest image
        if x_ji > ℝ[0.5*boxsize]:
            x_ji -= boxsize
        elif x_ji < ℝ[-0.5*boxsize]:
            x_ji += boxsize
        if y_ji > ℝ[0.5*boxsize]:
            y_ji -= boxsize
        elif y_ji < ℝ[-0.5*boxsize]:
            y_ji += boxsize
        if z_ji > ℝ[0.5*boxsize]:
            z_ji -= boxsize
        elif z_ji < ℝ[-0.5*boxsize]:
            z_ji += boxsize
        # The Ewald correction force for all images except the
        # nearest one, which might not be the actual particle.
        force_ij = ewald(x_ji, y_ji, z_ji)
        # Add in the force from the particle's nearest image
        r3 = (x_ji**2 + y_ji**2 + z_ji**2
            + ℝ[(0.5*(receiver.softening_length + supplier.softening_length))**2]
        )**1.5
        forcex_ij = force_ij[0] - x_ji*ℝ[1/r3]
        forcey_ij = force_ij[1] - y_ji*ℝ[1/r3]
        forcez_ij = force_ij[2] - z_ji*ℝ[1/r3]
        # Compute and apply momentum change
        # to particle i due to particle j.
        if apply_to_i:
            gravity_factor = gravity_factors[rung_index_i]
            momx_r[i] += forcex_ij*gravity_factor
            momy_r[i] += forcey_ij*gravity_factor
            momz_r[i] += forcez_ij*gravity_factor
        # Apply or save the momentum change of particle j
        # of the supplier (the external component).
        with unswitch:
            if 𝔹[not only_supply and rank == rank_supplier]:
                # This interaction is exlusively within the
                # local domain. Apply momentum changes
                # directly to particle j.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_j]
                    momx_s[j] -= forcex_ij*gravity_factor
                    momy_s[j] -= forcey_ij*gravity_factor
                    momz_s[j] -= forcez_ij*gravity_factor
            elif 𝔹[not only_supply]:
                # Add momentum change to the external
                # Δmom buffers of the supplier.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_j]
                    Δmomx_s[j] -= forcex_ij*gravity_factor
                    Δmomy_s[j] -= forcey_ij*gravity_factor
                    Δmomz_s[j] -= forcez_ij*gravity_factor

# Function implementing pairwise gravity (short-range only)
@cython.header(
    # Arguments
    receiver='Component',
    supplier='Component',
    pairing_level=str,
    tile_indices_receiver='Py_ssize_t[::1]',
    tile_indices_supplier='Py_ssize_t[::1]',
    rank_supplier='int',
    only_supply='bint',
    ᔑdt=dict,
    extra_args=dict,
    # Locals
    apply_to_i='bint',
    apply_to_j='bint',
    forcex_ij='double',
    forcey_ij='double',
    forcez_ij='double',
    gravity_factor='double',
    gravity_factors='double[::1]',
    i='Py_ssize_t',
    interaction_name=str,
    j='Py_ssize_t',
    momx_r='double*',
    momx_s='double*',
    momy_r='double*',
    momy_s='double*',
    momz_r='double*',
    momz_s='double*',
    r2='double',
    rung_index_i='signed char',
    rung_index_j='signed char',
    shortrange_factor='double',
    shortrange_index='Py_ssize_t',
    x_ji='double',
    y_ji='double',
    z_ji='double',
    Δmomx_s='double*',
    Δmomy_s='double*',
    Δmomz_s='double*',
    returns='void',
)
def gravity_pairwise_shortrange(
    receiver, supplier, pairing_level,
    tile_indices_receiver, tile_indices_supplier,
    rank_supplier, only_supply, ᔑdt, extra_args,
):
    # Extract variables from the receiver component
    momx_r = receiver.momx
    momy_r = receiver.momy
    momz_r = receiver.momz
    # Extract variables from the supplier (the external) component
    momx_s  = supplier.momx
    momy_s  = supplier.momy
    momz_s  = supplier.momz
    Δmomx_s = supplier.Δmomx
    Δmomy_s = supplier.Δmomy
    Δmomz_s = supplier.Δmomz
    # Construct array of factors used for momentum updates:
    #   Δmom = -r⃗/r³*G*mass_r*mass_s*Δt/a.
    # In the general case of decaying particles,
    # the mass of each particle is
    #   mass(a) = component.mass*a**(-3*component.w_eff(a=a)).
    # Below we integrate over the time dependence.
    # The array should be indexed with the rung_index
    # of the receiver particle.
    gravity_factors = G_Newton*receiver.mass*supplier.mass*ᔑdt[
        'a**(-3*w_eff₀-3*w_eff₁-1)', receiver.name, supplier.name]
    # Loop over all (receiver, supplier) particle pairs (i, j)
    interaction_name = 'gravity'
    for i, j, rung_index_i, rung_index_j, x_ji, y_ji, z_ji, apply_to_i, apply_to_j in particle_particle(
        receiver, supplier, pairing_level,
        tile_indices_receiver, tile_indices_supplier,
        rank_supplier, interaction_name, only_supply,
    ):
        # Translate coordinates so they correspond to the nearest image
        if x_ji > ℝ[0.5*boxsize]:
            x_ji -= boxsize
        elif x_ji < ℝ[-0.5*boxsize]:
            x_ji += boxsize
        if y_ji > ℝ[0.5*boxsize]:
            y_ji -= boxsize
        elif y_ji < ℝ[-0.5*boxsize]:
            y_ji += boxsize
        if z_ji > ℝ[0.5*boxsize]:
            z_ji -= boxsize
        elif z_ji < ℝ[-0.5*boxsize]:
            z_ji += boxsize
        r2 = x_ji**2 + y_ji**2 + z_ji**2
        # If the particle pair is separated by a distance larger
        # than the range of the short-range force,
        # ignore this interaction completely.
        if r2 > ℝ[shortrange_params['gravity']['cutoff']**2]:
            continue
        # Add softening
        r2 += ℝ[(0.5*(receiver.softening_length + supplier.softening_length))**2]
        # Compute the short-range force. Here the "force" is in units
        # of inverse length squared, given by
        # force = -r⃗/r³ (x/sqrt(π) exp(-x²/4) + erfc(x/2)),
        # where x = r/scale with scale the long/short-range
        # force split scale.
        # We have this whole expression except for r⃗ already tabulated.
        shortrange_index = int(r2*ℝ[(shortrange_table_size - 1)/shortrange_table_maxr2])
        shortrange_factor = shortrange_table_ptr[shortrange_index]
        forcex_ij = x_ji*shortrange_factor
        forcey_ij = y_ji*shortrange_factor
        forcez_ij = z_ji*shortrange_factor
        # Compute and apply momentum change to particle i due to
        # particle j, if particle i is on an active rung.
        if apply_to_i:
            gravity_factor = gravity_factors[rung_index_i]
            momx_r[i] += forcex_ij*gravity_factor
            momy_r[i] += forcey_ij*gravity_factor
            momz_r[i] += forcez_ij*gravity_factor
        # Apply or save the momentum change of particle j
        # of the supplier (the external component).
        with unswitch:
            if 𝔹[not only_supply and rank == rank_supplier]:
                # This interaction is exlusively within the
                # local domain. Apply momentum changes
                # directly to particle j.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_j]
                    momx_s[j] -= forcex_ij*gravity_factor
                    momy_s[j] -= forcey_ij*gravity_factor
                    momz_s[j] -= forcez_ij*gravity_factor
            elif 𝔹[not only_supply]:
                # Add momentum change to the external
                # Δmom buffers of the supplier.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_j]
                    Δmomx_s[j] -= forcex_ij*gravity_factor
                    Δmomy_s[j] -= forcey_ij*gravity_factor
                    Δmomz_s[j] -= forcez_ij*gravity_factor
# Helper function for the gravity_pairwise_shortrange function,
# which initializes the global shortrange table.
@cython.header(returns='void')
def tabulate_shortrange_gravity():
    """This function tabulates the short-range factor
    y = -r⁻³(x/sqrt(π)exp(-x²/4) + erfc(x/2))
    with x = r/scale where r is the distance between two particles
    and scale is the long/short-range force split scale.
    We only need this for 0 <= r <= cutoff, where cutoff is the maximum
    reach of the short-range force. However, due to softening we
    sometimes need to go a bit beyound cutoff. Just to be safe we
    tabulate out to 2*cutoff.
    """
    global shortrange_table, shortrange_table_ptr
    if shortrange_table is not None:
        return
    scale  = shortrange_params['gravity']['scale']
    r2 = np.linspace(0, shortrange_table_maxr2, shortrange_table_size)
    r = np.sqrt(r2)
    x = r/scale
    # Compute r⁻³. The zeroth element is r == 0.
    # Here we explicitly set r⁻³ to 0, corresponding to zero force in
    # the case of two particles sitting on top of each other.
    one_over_r3 = r.copy()
    one_over_r3[0] = 1
    one_over_r3 **= -3
    one_over_r3[0] = 0
    # Do the tabulation and populate global variables
    shortrange_table = -one_over_r3*(x/np.sqrt(π)*np.exp(-0.25*x**2) + scipy.special.erfc(0.5*x))
    shortrange_table_ptr = cython.address(shortrange_table[:])
# Global variables used by the tabulate_shortrange_gravity function
cython.declare(
    shortrange_table='double[::1]',
    shortrange_table_ptr='double*',
    shortrange_table_size='Py_ssize_t',
    shortrange_table_maxr2='double',
)
shortrange_table = None
shortrange_table_ptr = NULL
shortrange_table_size = 2**20
shortrange_table_maxr2 = (2*shortrange_params['gravity']['cutoff'])**2

# Function implementing pairwise gravity (non-periodic)
@cython.header(
    # Arguments
    receiver='Component',
    supplier='Component',
    pairing_level=str,
    tile_indices_receiver='Py_ssize_t[::1]',
    tile_indices_supplier='Py_ssize_t[::1]',
    rank_supplier='int',
    only_supply='bint',
    ᔑdt=dict,
    extra_args=dict,
    # Locals
    apply_to_i='bint',
    apply_to_j='bint',
    forcex_ij='double',
    forcey_ij='double',
    forcez_ij='double',
    gravity_factor='double',
    gravity_factors='double[::1]',
    i='Py_ssize_t',
    interaction_name=str,
    j='Py_ssize_t',
    momx_r='double*',
    momx_s='double*',
    momy_r='double*',
    momy_s='double*',
    momz_r='double*',
    momz_s='double*',
    r3='double',
    rung_index_i='signed char',
    rung_index_j='signed char',
    x_ji='double',
    y_ji='double',
    z_ji='double',
    Δmomx_s='double*',
    Δmomx_ij='double',
    Δmomy_s='double*',
    Δmomy_ij='double',
    Δmomz_s='double*',
    Δmomz_ij='double',
    returns='void',
)
def gravity_pairwise_nonperiodic(
    receiver, supplier, pairing_level,
    tile_indices_receiver, tile_indices_supplier,
    rank_supplier, only_supply, ᔑdt, extra_args,
):
    # Extract variables from the receiver component
    momx_r = receiver.momx
    momy_r = receiver.momy
    momz_r = receiver.momz
    # Extract variables from the supplier (the external) component
    momx_s  = supplier.momx
    momy_s  = supplier.momy
    momz_s  = supplier.momz
    Δmomx_s = supplier.Δmomx
    Δmomy_s = supplier.Δmomy
    Δmomz_s = supplier.Δmomz
    # Construct array of factors used for momentum updates:
    #   Δmom = -r⃗/r³*G*mass_r*mass_s*Δt/a.
    # In the general case of decaying particles,
    # the mass of each particle is
    #   mass(a) = component.mass*a**(-3*component.w_eff(a=a)).
    # Below we integrate over the time dependence.
    # The array should be indexed with the rung_index
    # of the receiver particle.
    gravity_factors = G_Newton*receiver.mass*supplier.mass*ᔑdt[
        'a**(-3*w_eff₀-3*w_eff₁-1)', receiver.name, supplier.name]
    # Loop over all (receiver, supplier) particle pairs (i, j)
    interaction_name = 'gravity'
    for i, j, rung_index_i, rung_index_j, x_ji, y_ji, z_ji, apply_to_i, apply_to_j in particle_particle(
        receiver, supplier, pairing_level,
        tile_indices_receiver, tile_indices_supplier,
        rank_supplier, interaction_name, only_supply,
    ):
        # The direct force on particle i from particle j
        r3 = (x_ji**2 + y_ji**2 + z_ji**2
            + ℝ[(0.5*(receiver.softening_length + supplier.softening_length))**2]
        )**1.5
        forcex_ij = x_ji*ℝ[-1/r3]
        forcey_ij = y_ji*ℝ[-1/r3]
        forcez_ij = z_ji*ℝ[-1/r3]
        # Compute and apply momentum change
        # to particle i due to particle j.
        if apply_to_i:
            gravity_factor = gravity_factors[rung_index_r]
            momx_r[i] += forcex_ij*gravity_factor
            momy_r[i] += forcey_ij*gravity_factor
            momz_r[i] += forcez_ij*gravity_factor
        # Apply or save the momentum change of particle j
        # of the supplier (the external component).
        with unswitch:
            if 𝔹[not only_supply and rank == rank_supplier]:
                # This interaction is exlusively within the
                # local domain. Apply momentum changes
                # directly to particle j.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_s]
                    momx_s[j] -= forcex_ij*gravity_factor
                    momy_s[j] -= forcey_ij*gravity_factor
                    momz_s[j] -= forcez_ij*gravity_factor
            elif 𝔹[not only_supply]:
                # Add momentum change to the external
                # Δmom buffers of the supplier.
                if apply_to_j:
                    gravity_factor = gravity_factors[rung_index_s]
                    Δmomx_s[j] -= forcex_ij*gravity_factor
                    Δmomy_s[j] -= forcey_ij*gravity_factor
                    Δmomz_s[j] -= forcez_ij*gravity_factor

# Function implementing the gravitational potential (in Fouier space).
# Here k2 = k² is the squared magnitude of the wave vector,
# in physical units.
@cython.header(
    k2='double',
    returns='double',
)
def gravity_potential(k2):
    return ℝ[-4*π*G_Newton]/k2

# Function implementing just the long-range part
# of the gravitational potential (in Fouier space).
# Here k2 = k² is the squared magnitude of the wave vector,
# in physical units.
@cython.header(
    k2='double',
    returns='double',
)
def gravity_longrange_potential(k2):
    return exp(-k2*ℝ[shortrange_params['gravity']['scale']**2])*gravity_potential(k2)

