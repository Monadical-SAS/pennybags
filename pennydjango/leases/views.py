from django.db.models import Sum
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.generic import CreateView, DetailView

from rest_framework import viewsets

from penny.model_utils import get_all_or_by_user
from penny.mixins import (
    ClientOrAgentRequiredMixin, AgentRequiredMixin, MainObjectContextMixin
)
from penny.utils import ExtendedEncoder
from listings.mixins import ListingContextMixin
from listings.serializer import PrivateListingSerializer
from leases.models import Lease, LeaseMember, MoveInCost
from leases.form import LeaseCreateForm, BasicLeaseMemberForm, MoveInCostForm
from leases.serializer import LeaseSerializer
from ui.views.base_views import PublicReactView


# React
class LeaseDetail(ClientOrAgentRequiredMixin, PublicReactView, DetailView):
    model = Lease
    title = 'Lease Detail'
    component = 'pages/lease.js'
    pk_url_kwarg = 'pk'
    template_name = 'leases/lease_agent.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        props = self.get_props(request, *args, **kwargs)
        if request.GET.get('props_json'):
            return JsonResponse(props, encoder=ExtendedEncoder)

        context = self.get_context(request, *args, **kwargs)
        context['props'] = props
        context.update(**self.get_context_data())
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lease_members = self.object.leasemember_set.select_related('user')
        move_in_costs = self.object.moveincost_set.order_by('-created')
        context['lease_members'] = lease_members
        context['move_in_costs'] = move_in_costs
        context['invite_member_form'] = BasicLeaseMemberForm()
        context['move_in_costs_form'] = MoveInCostForm(pk=self.object.id)
        context['total'] = MoveInCost.objects.total_by_offer(self.object.id)
        return context

    def props(self, request, *args, **kwargs):
        obj = self.get_object()

        return {
            'lease': LeaseSerializer(obj).data,
        }


class LeasesList(AgentRequiredMixin, PublicReactView):
    title = 'Leases Management'
    component = 'pages/leases.js'
    template = 'ui/react_base_card.html'

    def props(self, request, *args, **kwargs):
        constants = {
        }

        return {
            'constants': constants,
            'endpoint': '/leases/private/'
        }


class LeaseCreate(AgentRequiredMixin,
                  ListingContextMixin,
                  PublicReactView,
                  CreateView):
    model = Lease
    form_class = LeaseCreateForm
    title = 'Create Offer'
    component = 'pages/listing.js'
    template = 'leases/create.html'
    template_name = 'leases/create.html'

    def get(self, request, *args, **kwargs):
        self.object = None

        props = self.get_props(request, *args, **kwargs)
        if request.GET.get('props_json'):
            return JsonResponse(props, encoder=ExtendedEncoder)

        context = self.get_context(request, *args, **kwargs)
        context['props'] = props
        context.update(**self.get_context_data())

        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('leases:detail', args=[self.object.id])

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.listing = self.get_main_object()
        self.object.created_by = self.request.user
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def props(self, request, *args, **kwargs):
        return {
            'listing': PrivateListingSerializer(self.get_main_object()).data,
        }


# Django
class LeaseMemberCreate(MainObjectContextMixin, AgentRequiredMixin, CreateView):
    http_method_names = ['post']
    model = LeaseMember
    main_model = Lease
    form_class = BasicLeaseMemberForm

    def get_success_url(self):
        return reverse('leases:detail', args=[self.main_object.id])

    def form_valid(self, form):
        member = form.save(commit=False)
        member.offer = self.get_main_object()
        member.save()
        return HttpResponseRedirect(self.get_success_url())


class MoveInCostCreate(MainObjectContextMixin, AgentRequiredMixin, CreateView):
    http_method_names = ['post']
    model = MoveInCost
    main_model = Lease
    form_class = MoveInCostForm

    def form_valid(self, form):
        cost = form.save(commit=False)
        lease = self.get_main_object()
        cost.offer = lease
        cost.save()
        total = MoveInCost.objects.total_by_offer(lease.id)
        return JsonResponse(data={
            'status': 200,
            'total': total,
            'value': render_to_string('leases/move_in_cost.html', context={
                'charge': cost.charge,
                'value': cost.value
            })
        })

    def form_invalid(self, form):
        return JsonResponse(data={'status': 500, 'errors': form.errors})


# Rest Framework
class LeaseViewSet(AgentRequiredMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Lease.objects.all()
    serializer_class = LeaseSerializer

    def get_queryset(self):
        self.queryset = super().get_queryset()
        user = self.request.user
        self.queryset = get_all_or_by_user(
            Lease,
            user,
            'created_by',
            self.queryset
        )
        return self.queryset.order_by('-modified')
